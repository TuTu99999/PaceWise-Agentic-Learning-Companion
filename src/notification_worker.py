"""Independent notification worker; safe to scale separately from PDF/RAG."""

from __future__ import annotations

import logging
import time

from src.config import get_settings
from src.db import initialize_database
from src.services.sync_worker import record_worker_heartbeat
from src.services.web_push import (
    deliver_due_reminders,
    process_sqs_reminder_jobs,
    publish_due_reminder_jobs,
    recover_notification_leases,
)

logger = logging.getLogger("pacewise.notification-worker")


def run_notification_worker() -> None:
    settings = get_settings()
    while True:
        try:
            recover_notification_leases(settings)
            if settings.sqs_notification_queue_url:
                publish_due_reminder_jobs(settings)
                process_sqs_reminder_jobs(settings)
            else:
                deliver_due_reminders(settings)
            record_worker_heartbeat(settings, worker_kind="notification")
        except Exception as exc:
            # Never include provider responses, endpoints, payloads or tokens.
            logger.error("notification_worker_iteration_failed error_type=%s", type(exc).__name__)
        time.sleep(1 if settings.sqs_notification_queue_url else 30)


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    initialize_database()
    run_notification_worker()


if __name__ == "__main__":
    main()
