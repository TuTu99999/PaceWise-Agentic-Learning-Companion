"""Production configuration must fail closed before the server accepts traffic."""

import pytest
from pydantic import ValidationError

from src.config import Settings, get_settings
from tests.production_settings import valid_production_settings


def test_valid_production_configuration_forces_security_invariants(tmp_path):
    settings = Settings(
        **valid_production_settings(
            tmp_path,
            force_https=False,
            session_cookie_secure=False,
            private_api_required=False,
        )
    )

    assert settings.force_https
    assert settings.session_cookie_secure
    assert settings.private_api_required


def test_staging_uses_the_same_fail_closed_invariants(tmp_path):
    settings = Settings(**valid_production_settings(tmp_path, app_env="staging"))

    assert settings.force_https
    assert settings.session_cookie_secure
    assert settings.private_api_required

    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(**valid_production_settings(tmp_path, app_env="staging", database_url="sqlite:///data.db"))


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"database_url": "sqlite:///data.db"}, "DATABASE_URL"),
        ({"database_schema_revision": ""}, "DATABASE_SCHEMA_REVISION"),
        ({"database_schema_revision": "stale"}, "application revision"),
        ({"pacewise_session_secret": "development-only-change-this-session-secret"}, "PACEWISE_SESSION_SECRET"),
        ({"cors_origins": "http://localhost:5173"}, "CORS_ORIGINS"),
        ({"google_redirect_uri": "http://localhost:8000/callback"}, "GOOGLE_REDIRECT_URI"),
        ({"metrics_bearer_token": "short"}, "METRICS_BEARER_TOKEN"),
        ({"openai_api_key": ""}, "OPENAI_API_KEY"),
        ({"google_token_encryption_key": "invalid"}, "GOOGLE_TOKEN_ENCRYPTION_KEY"),
        ({"course_storage_backend": "local"}, "COURSE_STORAGE_BACKEND"),
        ({"allow_legacy_material_writes": True}, "ALLOW_LEGACY_MATERIAL_WRITES"),
        ({"course_source_mode": "external"}, "COURSE_SOURCE_MODE"),
        ({"course_upload_dir": "./data/uploads"}, "Local course material directories"),
        ({"s3_course_materials_bucket": ""}, "S3_COURSE_MATERIALS_BUCKET"),
        ({"s3_kms_key_id": ""}, "S3_KMS_KEY_ID"),
        ({"sqs_ingestion_queue_url": ""}, "SQS_INGESTION_QUEUE_URL"),
        ({"sqs_ingestion_dlq_url": ""}, "SQS_INGESTION_DLQ_URL"),
        ({"sqs_notification_queue_url": ""}, "SQS_NOTIFICATION_QUEUE_URL"),
        ({"sqs_notification_dlq_url": ""}, "SQS_NOTIFICATION_DLQ_URL"),
        ({"qdrant_url": "http://127.0.0.1:6333"}, "QDRANT_URL"),
        ({"qdrant_path": "./data/qdrant"}, "Local vector-store paths"),
        ({"trusted_proxy_cidrs": "not-a-network"}, "TRUSTED_PROXY_CIDRS"),
    ],
)
def test_invalid_production_configuration_is_rejected(tmp_path, override, message):
    with pytest.raises(ValidationError, match=message):
        Settings(**valid_production_settings(tmp_path, **override))


def test_mounted_secret_is_loaded_before_production_validation(tmp_path):
    mounted = tmp_path / "session-secret"
    mounted.write_text("mounted-session-secret-9Vx7!k2P4m6Q8r1T", encoding="utf-8")

    settings = Settings(
        **valid_production_settings(
            tmp_path,
            pacewise_session_secret="",
            pacewise_session_secret_file=str(mounted),
        )
    )

    assert settings.pacewise_session_secret == mounted.read_text(encoding="utf-8")


def test_production_settings_never_load_repository_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("PACEWISE_SESSION_SECRET=from-local-file\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()


def test_staging_settings_never_load_repository_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("PACEWISE_SESSION_SECRET=from-local-file\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "staging")
    get_settings.cache_clear()

    with pytest.raises(ValidationError, match="DATABASE_URL"):
        get_settings()

    get_settings.cache_clear()

    with pytest.raises(ValidationError, match="DATABASE_URL"):
        get_settings()

    get_settings.cache_clear()


def test_test_environment_uses_only_test_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("APP_NAME=wrong\n", encoding="utf-8")
    (tmp_path / ".env.test").write_text("APP_NAME=PaceWise test\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    assert get_settings().app_name == "PaceWise test"

    get_settings.cache_clear()
