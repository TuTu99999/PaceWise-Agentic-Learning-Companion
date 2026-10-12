"""Normalize request dates before persistence, including SQLite demo runs."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator


def as_utc(value: datetime) -> datetime:
    # Existing simulator API treats offset-less timestamps as UTC. UI sends ISO
    # instants with offsets; converting before persistence avoids losing +07:00.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


LMSDateTime = Annotated[datetime, AfterValidator(as_utc)]
