"""Explicitly prepare a disposable local SQLite development database."""

from sqlalchemy import text

from src import persistence_models  # noqa: F401
from src.api import course_uploads, google_signup  # noqa: F401
from src.config import get_settings
from src.course_source import models as course_models  # noqa: F401
from src.course_source.db import Base as CourseBase
from src.course_source.db import engine as course_engine
from src.db import Base, engine
from src.schema import SCHEMA_REVISION


def main() -> int:
    settings = get_settings()
    if settings.app_env != "development" or engine.dialect.name != "sqlite":
        raise SystemExit("This helper is only for the local SQLite development database")
    Base.metadata.create_all(engine)
    CourseBase.metadata.create_all(course_engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(64) PRIMARY KEY)"))
        connection.execute(text("DELETE FROM alembic_version"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                           {"revision": SCHEMA_REVISION})
    print(f"Local development database prepared at {SCHEMA_REVISION}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
