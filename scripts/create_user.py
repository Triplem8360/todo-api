from __future__ import annotations

import argparse
import asyncio
import secrets

from todo_api.core.config import get_settings
from todo_api.db.session import create_database
from todo_api.schemas.user import UserCreateSchema
from todo_api.services.auth import AuthService


def generate_password() -> str:
    return secrets.token_urlsafe(18)


async def create_user(
    email: str,
    full_name: str | None,
    superuser: bool,
) -> None:
    settings = get_settings()
    database = create_database(settings)
    password = generate_password()

    try:
        async with database.session_factory() as session:
            auth_service = AuthService(session=session, settings=settings)

            payload = UserCreateSchema(email=email, full_name=full_name, password=password)
            user = await auth_service.register(payload, is_superuser=superuser)

            print(f"Created user: {user.email}")
            print(f"Password (shown once): {password}")
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a user with an automatically generated password.",
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name")
    parser.add_argument("--superuser", action="store_true")
    args = parser.parse_args()

    asyncio.run(create_user(email=args.email, full_name=args.full_name, superuser=args.superuser))


if __name__ == "__main__":
    main()
