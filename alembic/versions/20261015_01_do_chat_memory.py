"""Encrypted ephemeral memory for Do learning-support chat."""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "20261015_01"
down_revision = "20261012_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns("pacewise_study_timer_sessions")}
    if "chat_json" not in columns:
        op.add_column(
            "pacewise_study_timer_sessions",
            sa.Column("chat_json", sa.Text(), nullable=False, server_default="[]"),
        )


def downgrade() -> None:
    raise RuntimeError("Do chat memory contains customer data and cannot be downgraded destructively")
