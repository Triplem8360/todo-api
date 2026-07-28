from __future__ import annotations

import argparse
import asyncio
from getpass import getpass

from todo_api.core.config import get_settings
from todo_api.db.session import create_database
from todo_api.schemas.user import UserCreateSchema
from todo_api.services.auth import register_user


async def create_user(email: str, full_name: str | None, superuser: bool) -> None:
    payload = UserCreateSchema(email=email, full_name=full_name, password=getpass())
    database = create_database(get_settings())
    try:
        async with database.session_factory() as session:
            user = await register_user(session, payload, is_superuser=superuser)
            print(f"Created user: {user.email}")
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a user interactively.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name")
    parser.add_argument("--superuser", action="store_true")
    args = parser.parse_args()
    asyncio.run(create_user(args.email, args.full_name, args.superuser))


if __name__ == "__main__":
    main()
