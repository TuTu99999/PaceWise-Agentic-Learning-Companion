"""Initial PaceWise schema baseline."""

from sqlalchemy import MetaData, inspect

from alembic import op

revision = "20261012_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names()) - {"alembic_version"}
    if existing:
        raise RuntimeError(
            "Refusing to stamp an unversioned non-empty database. "
            "Audit and adopt the legacy schema before running Alembic."
        )
    from src import persistence_models  # noqa: F401
    from src.api import course_uploads, google_signup  # noqa: F401
    from src.course_source import models as course_models  # noqa: F401
    from src.course_source.db import Base as CourseBase
    from src.db import Base

    Base.metadata.create_all(bind)
    op.execute('CREATE SCHEMA IF NOT EXISTS "course_source"')
    # Connection.execution_options mutates a SQLAlchemy 2.x connection in
    # place. Using schema_translate_map here would leak into Alembic's own
    # version-table insert. Clone the tables with an explicit schema instead.
    course_metadata = MetaData()
    for table in CourseBase.metadata.sorted_tables:
        table.to_metadata(course_metadata, schema="course_source")
    course_metadata.create_all(bind)


def downgrade() -> None:
    raise RuntimeError("The production baseline cannot be downgraded destructively")
