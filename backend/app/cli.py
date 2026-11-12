"""Operator commands. There is no self-service sign-up or admin UI in the MVP.

uv run python -m app.cli create-user --email expert@example.com --locale uk
uv run python -m app.cli revoke-sessions --email expert@example.com
"""

import argparse
import asyncio
import sys

from app.application.auth.sessions import SessionService
from app.application.ports import system_clock
from app.application.users import InvalidEmail, UserAlreadyExists, UserService
from app.config import get_settings
from app.domain.users import DEFAULT_LOCALE, Locale, normalize_email
from app.infrastructure.db.engine import create_engine, create_session_factory
from app.infrastructure.db.repositories import UserRepository


async def _create_user(email: str, locale: Locale, if_not_exists: bool) -> int:
    engine = create_engine(get_settings().database_url)
    try:
        async with create_session_factory(engine)() as db:
            try:
                await UserService(db).create_user(email=email, preferred_locale=locale)
            except InvalidEmail:
                print("Invalid email address.", file=sys.stderr)
                return 1
            except UserAlreadyExists:
                if if_not_exists:
                    print("User already exists.")
                    return 0
                print("User already exists.", file=sys.stderr)
                return 1
        print("User created.")
        return 0
    finally:
        await engine.dispose()


async def _revoke_sessions(email: str) -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:
        async with create_session_factory(engine)() as db:
            user = await UserRepository(db).get_by_email(normalize_email(email))
            if user is None:
                print("User not found.", file=sys.stderr)
                return 1
            count = await SessionService(db, settings, system_clock).revoke_all(user.id)
        print(f"Revoked {count} session(s).")
        return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-user", help="Create the expert account.")
    create.add_argument("--email", required=True)
    create.add_argument("--locale", choices=[loc.value for loc in Locale], default=DEFAULT_LOCALE)
    create.add_argument("--if-not-exists", action="store_true")

    revoke = commands.add_parser("revoke-sessions", help="Sign a user out everywhere.")
    revoke.add_argument("--email", required=True)

    args = parser.parse_args(argv)
    if args.command == "create-user":
        return asyncio.run(_create_user(args.email, Locale(args.locale), args.if_not_exists))
    return asyncio.run(_revoke_sessions(args.email))


if __name__ == "__main__":
    sys.exit(main())
