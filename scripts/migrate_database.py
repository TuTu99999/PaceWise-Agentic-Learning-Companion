"""Run the ordered Alembic schema job before replacing ECS tasks."""

from __future__ import annotations

from alembic.config import Config
from sqlalchemy import text

from alembic import command
from src.config import get_settings
from src.db import engine
from src.schema import SCHEMA_REVISION


def main() -> int:
    settings = get_settings()
    if settings.app_env not in {"staging", "production"}:
        raise SystemExit("Database migration must run with APP_ENV=staging or APP_ENV=production")
    if engine.dialect.name != "postgresql":
        raise SystemExit("Production migration requires PostgreSQL")

    command.upgrade(Config("alembic.ini"), "head")
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != SCHEMA_REVISION:
        raise SystemExit(f"Migration ended at {revision!r}, expected {SCHEMA_REVISION!r}")
    print(f"Database migrated to {revision}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
