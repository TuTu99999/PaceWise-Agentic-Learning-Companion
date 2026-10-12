from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import get_settings
from src.schema import SCHEMA_REVISION


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict:
    return {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}


settings = get_settings()
database = make_url(settings.database_url)
if database.get_backend_name() == "sqlite" and database.database not in {None, "", ":memory:"}:
    Path(database.database).expanduser().parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def initialize_database() -> None:
    from sqlalchemy import text

    from src import persistence_models  # noqa: F401

    current = get_settings()
    if current.app_env == "test":
        # Test fixtures own disposable databases; runtime environments never
        # create or mutate schema during process startup.
        Base.metadata.create_all(engine)
        return
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    except Exception as exc:
        raise RuntimeError("database is not migrated; run the schema migration job before startup") from exc
    expected = current.database_schema_revision or SCHEMA_REVISION
    if revision != expected:
        raise RuntimeError(f"database schema revision mismatch: found {revision!r}, expected {expected!r}")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
