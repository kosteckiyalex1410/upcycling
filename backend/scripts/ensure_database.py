"""Create the database named in UPCYCLING_DATABASE_URL if it does not exist (dev/CI/e2e only).

uv run python -m scripts.ensure_database
"""

import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import get_settings


def main() -> int:
    url = make_url(get_settings().database_url)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            )
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
                print("Database created.")
    finally:
        admin.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
