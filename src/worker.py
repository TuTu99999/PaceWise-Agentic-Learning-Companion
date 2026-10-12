"""Standalone PaceWise projection/PDF/RAG worker (no notifications)."""

import asyncio
import logging

from src.config import get_settings
from src.db import initialize_database
from src.services.sync_worker import run_worker


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    # HTTPX's INFO logs expose full internal URLs and actor/course query IDs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    initialize_database()
    if settings.course_source_mode == "standalone":
        from src.course_source.db import initialize_database as initialize_course_source

        initialize_course_source()
    asyncio.run(run_worker(settings))


if __name__ == "__main__":
    main()
