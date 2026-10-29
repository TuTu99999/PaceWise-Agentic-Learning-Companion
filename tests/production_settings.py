"""Deterministic valid production settings for fail-fast configuration tests."""

from pathlib import Path

from cryptography.fernet import Fernet


def valid_production_settings(tmp_path: Path, **overrides) -> dict:
    customer_key = tmp_path / "customer-data.key"
    customer_key.write_bytes(b"k" * 64)
    values = {
        "_env_file": None,
        "app_env": "production",
        "course_source_mode": "standalone",
        "database_url": "postgresql+psycopg://pacewise:secret@db.internal/pacewise",
        "database_schema_revision": "20261015_01",
        "cors_origins": "https://app.pacewise.test",
        "pacewise_session_secret": "prod-session-secret-4Qk9!x2N7v5L8c1B",
        "metrics_bearer_token": "metrics-token-4Qk9!x2N7v5L8c1B-rotate",
        "openai_api_key": "provider-key-for-test",
        "google_client_id": "google-client.apps.googleusercontent.com",
        "google_client_secret": "google-client-secret",
        "google_token_encryption_key": Fernet.generate_key().decode(),
        "google_redirect_uri": "https://app.pacewise.test/api/v1/integrations/google-calendar/callback",
        "google_oauth_success_url": "https://app.pacewise.test/app#/settings",
        "course_storage_backend": "s3",
        "course_upload_dir": "",
        "course_mock_file_dir": "",
        "s3_course_materials_bucket": "pacewise-course-materials-test",
        "s3_kms_key_id": "alias/pacewise-course-materials",
        "qdrant_url": "https://qdrant.pacewise.test",
        "qdrant_path": "",
        "chroma_persist_dir": "",
        "trusted_proxy_cidrs": "10.0.0.0/8",
        "customer_data_key_file": str(customer_key),
        "sqs_ingestion_queue_url": "https://sqs.ap-southeast-1.amazonaws.com/123456789012/pacewise-ingestion",
        "sqs_ingestion_dlq_url": "https://sqs.ap-southeast-1.amazonaws.com/123456789012/pacewise-ingestion-dlq",
        "sqs_notification_queue_url": "https://sqs.ap-southeast-1.amazonaws.com/123456789012/pacewise-notification",
        "sqs_notification_dlq_url": "https://sqs.ap-southeast-1.amazonaws.com/123456789012/pacewise-notification-dlq",
    }
    values.update(overrides)
    return values
