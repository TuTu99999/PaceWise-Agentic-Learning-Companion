"""A separate SQL namespace in the existing PaceWise database, not a service."""

from collections.abc import Generator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.db import engine as pacewise_engine

SCHEMA = "course_source"


class Base(DeclarativeBase):
    metadata = MetaData()


if pacewise_engine.dialect.name == "postgresql":
    engine = pacewise_engine.execution_options(schema_translate_map={None: SCHEMA})
else:
    # Isolated SQLite store for offline tests. PostgreSQL production uses one DB.
    url = pacewise_engine.url
    database = url.database
    if database in {None, "", ":memory:"}:
        from sqlalchemy.pool import StaticPool

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    else:
        engine = create_engine(url.set(database=database + ".courses"), connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as db:
        yield db


def initialize_database() -> None:
    from src.config import get_settings
    from src.course_source import models  # noqa: F401

    current = get_settings()
    if current.app_env == "test":
        Base.metadata.create_all(engine)
        return
    from sqlalchemy import inspect

    schema = SCHEMA if engine.dialect.name == "postgresql" else None
    if not inspect(engine).has_table("courses", schema=schema):
        raise RuntimeError("course_source schema is not migrated; run the schema migration job before startup")
    # Never seed, rename, normalize, or overwrite preserved source records.
