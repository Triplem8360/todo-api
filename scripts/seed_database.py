from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import os
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from faker import Faker
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from todo_api.core.config import get_settings
from todo_api.db.session import create_database
from todo_api.models import (
    APIKey,
    OAuthAuthorizationCode,
    RefreshSession,
    Todo,
    TodoPriority,
    TodoStatus,
    User,
)
from todo_api.schemas.user import UserCreateSchema
from todo_api.services.auth import AuthService

FAKER_LOCALE = "fa_IR"
DEFAULT_PASSWORD = "qwe123!@#"
SEED_EMAIL_DOMAIN = "example.com"


@dataclass(frozen=True, slots=True)
class SeedOptions:
    seed: int
    users: int
    todos_per_user: int
    api_keys_per_user: int
    refresh_sessions_per_user: int
    oauth_codes_per_user: int
    password: str
    oauth_client_id: str
    oauth_redirect_uri: str


@dataclass(frozen=True, slots=True)
class SeedResult:
    users: int
    todos: int
    api_keys: int
    refresh_sessions: int
    oauth_codes: int


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def seed_email(seed: int, index: int) -> str:
    return f"seed-{seed}-{index:04d}@{SEED_EMAIL_DOMAIN}"


def clean_sentence(value: str, *, max_length: int) -> str:
    cleaned = " ".join(value.split()).strip(" .،؛")
    return cleaned[:max_length].rstrip()


async def remove_previous_seed_batch(session: AsyncSession, seed: int) -> None:
    email_pattern = f"seed-{seed}-%@{SEED_EMAIL_DOMAIN}"
    await session.execute(delete(User).where(User.email.like(email_pattern)))
    await session.commit()


async def create_users(
    session: AsyncSession,
    *,
    settings: Settings,
    options: SeedOptions,
    fake: Faker,
    rng: random.Random,
) -> list[User]:
    auth_service = AuthService(session=session, settings=settings)
    users: list[User] = []
    inactive_user_ids: list[int] = []

    for index in range(1, options.users + 1):
        payload = UserCreateSchema(
            email=seed_email(options.seed, index),
            full_name=fake.name(),
            password=options.password,
        )

        user = await auth_service.register(
            payload,
            is_superuser=index == 1,
        )
        users.append(user)

        if index != 1 and rng.random() < 0.1:
            inactive_user_ids.append(user.id)

    if inactive_user_ids:
        await session.execute(
            update(User).where(User.id.in_(inactive_user_ids)).values(is_active=False)
        )
        await session.commit()

    return users


def build_todo(
    *,
    user_id: int,
    fake: Faker,
    rng: random.Random,
    now: datetime,
) -> Todo:
    status = rng.choice(list(TodoStatus))
    created_at = now - timedelta(days=rng.randint(0, 120), hours=rng.randint(0, 23))

    completed_at: datetime | None = None
    if status is TodoStatus.DONE:
        completed_at = created_at + timedelta(
            hours=rng.randint(1, 240),
            minutes=rng.randint(0, 59),
        )
        completed_at = min(completed_at, now)

    due_at = created_at + timedelta(days=rng.randint(-10, 45))
    description = None
    if rng.random() < 0.8:
        description = clean_sentence(fake.paragraph(nb_sentences=3), max_length=1_000)

    return Todo(
        user_id=user_id,
        title=clean_sentence(fake.sentence(nb_words=6), max_length=200),
        description=description,
        status=status,
        priority=rng.choice(list(TodoPriority)),
        due_at=due_at if rng.random() < 0.85 else None,
        completed_at=completed_at,
        is_archived=status in {TodoStatus.DONE, TodoStatus.CANCELLED} and rng.random() < 0.45,
        created_at=created_at,
        updated_at=completed_at or created_at,
    )


def build_api_key(
    *,
    seed: int,
    user_id: int,
    index: int,
    rng: random.Random,
    now: datetime,
) -> APIKey:
    created_at = now - timedelta(days=rng.randint(0, 90))
    return APIKey(
        user_id=user_id,
        name=f"کلید توسعه {index}",
        key_hash=sha256_hex(f"api-key:{seed}:{user_id}:{index}"),
        is_active=rng.random() >= 0.2,
        created_at=created_at,
        updated_at=created_at,
    )


def build_refresh_session(
    *,
    seed: int,
    user_id: int,
    index: int,
    rng: random.Random,
    now: datetime,
) -> RefreshSession:
    created_at = now - timedelta(days=rng.randint(0, 20), hours=rng.randint(0, 23))
    absolute_expires_at = created_at + timedelta(days=rng.randint(30, 90))
    expires_at = min(
        now + timedelta(days=rng.randint(1, 14)),
        absolute_expires_at,
    )

    was_rotated = rng.random() < 0.4
    is_revoked = rng.random() < 0.2
    activity_at = min(created_at + timedelta(days=1), now)

    return RefreshSession(
        id=sha256_hex(f"session-id:{seed}:{user_id}:{index}")[:64],
        user_id=user_id,
        token_hash=sha256_hex(f"refresh-token:{seed}:{user_id}:{index}:current"),
        previous_token_hash=(
            sha256_hex(f"refresh-token:{seed}:{user_id}:{index}:previous") if was_rotated else None
        ),
        expires_at=expires_at,
        absolute_expires_at=absolute_expires_at,
        revoked_at=activity_at if is_revoked else None,
        last_used_at=activity_at if was_rotated or is_revoked else None,
        rotated_at=activity_at if was_rotated else None,
        created_at=created_at,
        updated_at=activity_at if was_rotated or is_revoked else created_at,
    )


def build_oauth_code(
    *,
    seed: int,
    user_id: int,
    index: int,
    client_id: str,
    redirect_uri: str,
    rng: random.Random,
    now: datetime,
) -> OAuthAuthorizationCode:
    created_at = now - timedelta(minutes=rng.randint(0, 5))
    expires_at = created_at + timedelta(minutes=10)
    verifier = hashlib.sha256(f"pkce-verifier:{seed}:{user_id}:{index}".encode("utf-8")).hexdigest()
    consumed_at = None

    if rng.random() < 0.35:
        consumed_at = min(created_at + timedelta(minutes=1), expires_at)

    return OAuthAuthorizationCode(
        code_hash=sha256_hex(f"authorization-code:{seed}:{user_id}:{index}"),
        user_id=user_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=create_pkce_challenge(verifier),
        expires_at=expires_at,
        consumed_at=consumed_at,
        created_at=created_at,
        updated_at=consumed_at or created_at,
    )


async def create_related_data(
    session: AsyncSession,
    *,
    users: list[User],
    options: SeedOptions,
    fake: Faker,
    rng: random.Random,
) -> SeedResult:
    now = datetime.now(UTC)
    objects: list[object] = []

    todo_count = 0
    api_key_count = 0
    refresh_session_count = 0
    oauth_code_count = 0

    for user in users:
        for _ in range(options.todos_per_user):
            objects.append(build_todo(user_id=user.id, fake=fake, rng=rng, now=now))
            todo_count += 1

        for index in range(1, options.api_keys_per_user + 1):
            objects.append(
                build_api_key(
                    seed=options.seed,
                    user_id=user.id,
                    index=index,
                    rng=rng,
                    now=now,
                )
            )
            api_key_count += 1

        for index in range(1, options.refresh_sessions_per_user + 1):
            objects.append(
                build_refresh_session(
                    seed=options.seed,
                    user_id=user.id,
                    index=index,
                    rng=rng,
                    now=now,
                )
            )
            refresh_session_count += 1

        for index in range(1, options.oauth_codes_per_user + 1):
            objects.append(
                build_oauth_code(
                    seed=options.seed,
                    user_id=user.id,
                    index=index,
                    client_id=options.oauth_client_id,
                    redirect_uri=options.oauth_redirect_uri,
                    rng=rng,
                    now=now,
                )
            )
            oauth_code_count += 1

    session.add_all(objects)
    await session.commit()

    return SeedResult(
        users=len(users),
        todos=todo_count,
        api_keys=api_key_count,
        refresh_sessions=refresh_session_count,
        oauth_codes=oauth_code_count,
    )


async def seed_database(options: SeedOptions) -> SeedResult:
    fake = Faker(FAKER_LOCALE)
    fake.seed_instance(options.seed)
    rng = random.Random(options.seed)

    settings = get_settings()
    database = create_database(settings)

    try:
        async with database.session_factory() as session:
            await remove_previous_seed_batch(session, options.seed)

            users = await create_users(
                session,
                settings=settings,
                options=options,
                fake=fake,
                rng=rng,
            )

            return await create_related_data(
                session,
                users=users,
                options=options,
                fake=fake,
                rng=rng,
            )
    finally:
        await database.dispose()


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be zero or greater")
    return parsed


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be one or greater")
    return parsed


def parse_args() -> SeedOptions:
    parser = argparse.ArgumentParser(
        description="Seed the local database with deterministic Persian fake data."
    )
    parser.add_argument("--seed", type=int, default=1405)
    parser.add_argument("--users", type=positive_int, default=10)
    parser.add_argument("--todos-per-user", type=non_negative_int, default=10)
    parser.add_argument("--api-keys-per-user", type=non_negative_int, default=2)
    parser.add_argument(
        "--refresh-sessions-per-user",
        type=non_negative_int,
        default=2,
    )
    parser.add_argument("--oauth-codes-per-user", type=non_negative_int, default=1)
    parser.add_argument(
        "--password",
        default=os.getenv("TODO_API_SEED_PASSWORD", DEFAULT_PASSWORD),
        help="Password assigned to every seeded user.",
    )
    parser.add_argument("--oauth-client-id", default="todo-web")
    parser.add_argument(
        "--oauth-redirect-uri",
        default="http://localhost:3000/callback",
    )
    args = parser.parse_args()

    return SeedOptions(
        seed=args.seed,
        users=args.users,
        todos_per_user=args.todos_per_user,
        api_keys_per_user=args.api_keys_per_user,
        refresh_sessions_per_user=args.refresh_sessions_per_user,
        oauth_codes_per_user=args.oauth_codes_per_user,
        password=args.password,
        oauth_client_id=args.oauth_client_id,
        oauth_redirect_uri=args.oauth_redirect_uri,
    )


def main() -> None:
    options = parse_args()
    result = asyncio.run(seed_database(options))

    print("Database seed completed:")
    print(f"  users: {result.users}")
    print(f"  todos: {result.todos}")
    print(f"  API keys: {result.api_keys}")
    print(f"  refresh sessions: {result.refresh_sessions}")
    print(f"  OAuth authorization codes: {result.oauth_codes}")
    print(f"  first user: {seed_email(options.seed, 1)}")
    print("  first user is a superuser")


if __name__ == "__main__":
    main()
