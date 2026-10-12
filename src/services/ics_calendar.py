"""RFC 5545-compatible calendar export without an external account."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from src.models.calendar import CalendarBlock


def _escape(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str, limit: int = 75) -> list[str]:
    """Fold content lines without splitting UTF-8 code points."""
    output: list[str] = []
    current = ""
    current_size = 0
    prefix = ""
    for character in line:
        size = len(character.encode("utf-8"))
        if current and current_size + size > limit:
            output.append(prefix + current)
            current = character
            current_size = size
            prefix = " "
            limit = 74
        else:
            current += character
            current_size += size
    output.append(prefix + current)
    return output


def _utc_stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def build_ics(user_id: int, calendar_name: str, blocks: list[CalendarBlock]) -> bytes:
    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//PaceWise//Study Plan//VI",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
    ]
    for block in blocks:
        digest = hashlib.sha256(f"{user_id}:{block.block_id}".encode()).hexdigest()[:32]
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{digest}@pacewise.local",
                f"DTSTAMP:{now}",
                f"DTSTART:{_utc_stamp(block.start)}",
                f"DTEND:{_utc_stamp(block.end)}",
                f"SUMMARY:{_escape(block.title)}",
                "DESCRIPTION:Study block exported from PaceWise.",
                "TRANSP:OPAQUE",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    folded = [part for line in lines for part in _fold(line)]
    return ("\r\n".join(folded) + "\r\n").encode("utf-8")
