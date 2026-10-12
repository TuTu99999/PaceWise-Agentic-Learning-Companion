"""Alembic environment for the PaceWise and course_source schemas."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from src import persistence_models  # noqa: F401
from src.api import course_uploads, google_signup  # noqa: F401
from src.config import get_settings
from src.course_source import models as course_models  # noqa: F401
from src.course_source.db import Base as CourseBase
from src.db import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
target_metadata = [Base.metadata, CourseBase.metadata]


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"}, include_schemas=True,
                      compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}),
                                     prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          include_schemas=True, compare_type=True)
        with context.begin_transaction():
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(73422011)")
            context.run_migrations()


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
