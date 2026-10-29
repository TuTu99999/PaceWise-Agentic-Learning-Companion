import base64
import ipaddress
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.schema import SCHEMA_REVISION


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Environment files are selected explicitly by ``get_settings``.
        # Production never reads secrets from a repository-side .env file.
        env_file=None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AI20K Agent"
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    institution_id: str = "university-x"
    app_timezone: str = "Asia/Ho_Chi_Minh"
    aws_region: str = "ap-southeast-1"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:5173"
    trusted_proxy_cidrs: str = "127.0.0.1/32,::1/128"
    max_request_body_mb: int = Field(default=55, ge=1, le=250)
    readiness_timeout_seconds: float = Field(default=2.0, ge=0.2, le=10.0)

    # Standalone owns accounts/course records; external retains optional LMS integration.
    course_source_mode: Literal["standalone", "external"] = "standalone"
    course_storage_backend: Literal["local", "s3"] = "local"
    course_upload_dir: str = "./data/course-source/uploads"
    course_mock_file_dir: str = "./data/course-source/mock-files"
    s3_course_materials_bucket: str = ""
    s3_kms_key_id: str = ""
    course_pdf_max_mb: int = Field(default=50, ge=1, le=200)
    course_pdf_max_pages: int = Field(default=1000, ge=1, le=5000)
    course_file_max_chunks: int = Field(default=2000, ge=1, le=10000)
    course_file_max_text_chars: int = Field(default=4_000_000, ge=1000, le=20_000_000)
    course_file_processing_seconds: int = Field(default=120, ge=1, le=600)
    course_file_batch_size: int = Field(default=4, ge=1, le=20)
    course_file_queue_limit: int = Field(default=100, ge=1, le=1000)
    # The service key never leaves the backend.
    lms_base_url: str = "http://127.0.0.1:8010"
    pacewise_api_key: str = ""
    pacewise_api_key_file: str = ""
    pacewise_session_secret: str = "development-only-change-this-session-secret"
    pacewise_session_secret_file: str = ""
    pacewise_session_cookie: str = "pacewise_session"
    pacewise_csrf_cookie: str = "pacewise_csrf"
    pacewise_session_minutes: int = Field(default=240, ge=5, le=1440)
    session_cookie_secure: bool = False
    login_rate_limit: int = Field(default=5, ge=1, le=100)
    login_rate_window_seconds: int = Field(default=600, ge=60, le=86400)
    upload_ticket_rate_limit: int = Field(default=10, ge=1, le=100)
    upload_ticket_rate_window_seconds: int = Field(default=60, ge=10, le=900)
    lms_sync_interval_seconds: int = Field(default=30, ge=5, le=3600)
    worker_batch_size: int = Field(default=100, ge=1, le=500)
    worker_lease_seconds: int = Field(default=300, ge=30, le=3600)
    worker_max_attempts: int = Field(default=3, ge=1, le=20)
    sqs_ingestion_queue_url: str = ""
    sqs_ingestion_dlq_url: str = ""
    sqs_notification_queue_url: str = ""
    sqs_notification_dlq_url: str = ""
    sqs_wait_time_seconds: int = Field(default=10, ge=1, le=20)
    force_https: bool = False
    # Migration escape hatch only. Normal deployments manage all new materials on LMS.
    allow_legacy_material_writes: bool = False

    # Google Calendar OAuth. Keep the client secret and token-encryption key on
    # the server; neither value is ever returned to the browser.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_client_secret_file: str = ""
    google_token_encryption_key: str = ""
    google_token_encryption_key_file: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/integrations/google-calendar/callback"
    google_oauth_success_url: str = "http://localhost:5173/app#/settings"
    google_calendar_scopes: str = (
        "openid email "
        "https://www.googleapis.com/auth/calendar.freebusy "
        "https://www.googleapis.com/auth/calendar.events.owned"
    )
    # Conservative shared limits, below the project's actual Google Cloud quotas.
    google_api_project_per_minute: int = Field(default=1500, ge=1, le=100000)
    google_api_user_per_minute: int = Field(default=60, ge=1, le=600)
    google_api_daily_budget: int = Field(default=50000, ge=1, le=1000000)
    google_api_max_concurrent: int = Field(default=16, ge=1, le=100)
    google_api_cache_seconds: int = Field(default=300, ge=0, le=3600)
    private_api_required: bool = False
    private_api_key_file: str = "./data/private-api-p256.pem"
    customer_data_key_file: str = "./data/customer-data.key"
    google_signup_enabled: bool = True
    # Demo onboarding: verified Gmail students receive the active, published
    # catalog owned by one explicitly configured source instructor. This keeps
    # other instructors' courses isolated while allowing the source instructor
    # to add future courses without maintaining a code allowlist.
    google_signup_auto_enroll_courses: bool = True
    google_signup_auto_enroll_teacher_email: str = "teacher1@pacewise.edu.vn"

    # Web Push: localhost can use a persistent, automatically generated dev key.
    # Production must mount a stable private key and set a real contact address.
    webpush_enabled: bool = True
    webpush_private_key_file: str = "./data/webpush-vapid.pem"
    webpush_subject: str = "mailto:pacewise@example.com"

    # LLM
    openai_api_key: str = ""
    openai_base_url: str = "https://openrouter.ai/api/v1"
    model_name: str = "openai/gpt-4o-mini"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    llm_timeout_seconds: float = Field(default=45.0, ge=5.0, le=180.0)
    llm_max_output_tokens: int = Field(default=800, ge=64, le=4096)
    qa_max_output_tokens: int = Field(default=450, ge=128, le=1200)
    semantic_safety_mode: Literal["signals", "all"] = "signals"
    llm_input_cost_per_million: float = Field(default=0.0, ge=0.0)
    llm_output_cost_per_million: float = Field(default=0.0, ge=0.0)
    llm_fast_model: str = ""
    llm_reasoning_model: str = ""
    llm_max_concurrent: int = Field(default=8, ge=1, le=64)
    llm_max_waiting: int = Field(default=32, ge=0, le=256)
    llm_queue_timeout_seconds: float = Field(default=1.0, ge=0.01, le=10.0)
    llm_cache_ttl_seconds: int = Field(default=300, ge=0, le=3600)
    llm_cache_max_entries: int = Field(default=256, ge=1, le=4096)
    # Shared PostgreSQL admission, adapted from TheAnh/042adab.
    ai_rate_limit_enabled: bool = True
    ai_ip_requests_per_minute: int = Field(default=1000, ge=1, le=10000)
    ai_burst_requests: int = Field(default=3, ge=1, le=1000)
    ai_burst_window_seconds: int = Field(default=10, ge=1, le=3600)
    ai_requests_per_minute: int = Field(default=10, ge=1, le=10000)
    ai_requests_per_hour: int = Field(default=60, ge=1, le=100000)
    # Zero disables the daily token quota. Production keeps a finite default;
    # local/demo environments may explicitly opt out without disabling spam protection.
    ai_daily_token_limit_per_user: int = Field(default=2000000, ge=0)
    ai_estimated_tokens_per_request: int = Field(default=8000, ge=1)
    ai_max_concurrent_per_user: int = Field(default=1, ge=1, le=100)
    ai_max_concurrent_global: int = Field(default=10, ge=1, le=10000)
    ai_reservation_ttl_seconds: int = Field(default=600, ge=300, le=3600)
    ai_daily_budget_usd: float = Field(default=0.0, ge=0.0)
    ai_institution_daily_budget_usd: float = Field(default=0.0, ge=0.0)
    ai_text_request_weight: int = Field(default=1, ge=1, le=100)
    ai_image_request_weight: int = Field(default=3, ge=1, le=100)
    langsmith_enabled: bool = False
    # Reuse existing legacy credentials without copying secrets into another file.
    # Explicit modern configuration (including an empty value) takes precedence.
    langsmith_api_key: str = Field(
        default="",
        repr=False,
        validation_alias=AliasChoices("langsmith_api_key", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"),
    )
    langsmith_project: str = "pacewise-private-metadata"
    langsmith_workspace_id: str = Field(
        default="",
        validation_alias=AliasChoices("langsmith_workspace_id", "LANGSMITH_WORKSPACE_ID", "LANGCHAIN_WORKSPACE_ID"),
    )
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # Database
    database_url: str = "sqlite:///./data/pacewise.db"
    database_schema_revision: str = ""
    use_postgres_checkpoint: bool = True

    # Vector Store
    vector_store_type: str = "qdrant"
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_path: str = "./data/qdrant"
    chroma_persist_dir: str = "./src/agents/data/chroma"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_cache_dir: str = "./data/models/fastembed"
    embedding_threads: int = Field(default=1, ge=1, le=8)
    # Compact ONNX cross-encoder. Dense multilingual retrieval remains the
    # primary scope gate; reranking only orders candidates that already pass it.
    reranker_model: str = "ms-marco-TinyBERT-L-2-v2"
    reranker_cache_dir: str = "./data/models/flashrank"
    rag_top_k: int = Field(default=8, ge=3, le=30)
    rag_final_k: int = Field(default=3, ge=1, le=10)
    rag_rerank_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    rag_min_candidate_score: float = Field(default=0.4, ge=0.0, le=1.0)
    rag_score_threshold: float = Field(default=0.72, ge=0.0, le=1.0)
    rag_cache_ttl_seconds: int = Field(default=600, ge=0, le=3600)
    rag_cache_max_entries: int = Field(default=512, ge=1, le=4096)
    # Load both ONNX sessions during application startup so the first student
    # question does not pay the embedding/reranker cold-start cost. Deployments
    # that are tighter on memory can still opt out explicitly through the env.
    rag_warm_on_startup: bool = True
    metrics_enabled: bool = True
    metrics_bearer_token: str = ""
    assessment_retention_delay_hours: int = Field(default=48, ge=24, le=720)

    def model_post_init(self, __context: object) -> None:
        """Support Docker/Kubernetes/cloud secrets mounted as read-only files."""
        for value_field, file_field in (
            ("pacewise_api_key", "pacewise_api_key_file"),
            ("pacewise_session_secret", "pacewise_session_secret_file"),
            ("google_client_secret", "google_client_secret_file"),
            ("google_token_encryption_key", "google_token_encryption_key_file"),
        ):
            secret_file = getattr(self, file_field).strip()
            if secret_file:
                try:
                    value = Path(secret_file).read_text(encoding="utf-8").strip()
                except OSError as exc:
                    raise ValueError(f"Cannot read mounted secret {file_field}") from exc
                setattr(self, value_field, value)
        if self.app_env in {"staging", "production"}:
            # These protections are invariants, not deployment toggles.
            self.force_https = True
            self.session_cookie_secure = True
            self.private_api_required = True
            self._validate_production()

    @staticmethod
    def _is_local_url(value: str) -> bool:
        host = (urlparse(value.strip()).hostname or "").rstrip(".").casefold()
        if not host:
            return True
        if host == "localhost" or host.endswith(".localhost"):
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    @staticmethod
    def _valid_fernet_key(value: str) -> bool:
        try:
            return len(base64.urlsafe_b64decode(value.encode())) == 32
        except (ValueError, TypeError):
            return False

    def _validate_production(self) -> None:
        errors: list[str] = []
        if not self.database_url.casefold().startswith(("postgresql://", "postgresql+psycopg://")):
            errors.append("DATABASE_URL must use PostgreSQL")
        if not self.database_schema_revision.strip():
            errors.append("DATABASE_SCHEMA_REVISION is required")
        elif self.database_schema_revision != SCHEMA_REVISION:
            errors.append(f"DATABASE_SCHEMA_REVISION must equal application revision {SCHEMA_REVISION}")

        secret = self.pacewise_session_secret.strip()
        weak_secrets = {"", "change-me", "secret", "development-only-change-this-session-secret"}
        if len(secret) < 32 or secret.casefold() in weak_secrets or len(set(secret)) < 12:
            errors.append("PACEWISE_SESSION_SECRET must be a strong unique value of at least 32 characters")
        if len(self.metrics_bearer_token.strip()) < 32:
            errors.append("METRICS_BEARER_TOKEN must contain at least 32 characters")
        if not self.openai_api_key.strip():
            errors.append("OPENAI_API_KEY is required for the configured AI provider")
        if self.course_source_mode != "standalone":
            errors.append("COURSE_SOURCE_MODE must be standalone; the LMS simulator is not a production dependency")

        origins = [item.strip() for item in self.cors_origins.split(",") if item.strip()]
        if not origins or "*" in origins or any(self._is_local_url(item) for item in origins):
            errors.append("CORS_ORIGINS must contain explicit non-local HTTPS origins")
        elif any(urlparse(item).scheme != "https" for item in origins):
            errors.append("CORS_ORIGINS must use HTTPS")
        for name, value in (
            ("GOOGLE_REDIRECT_URI", self.google_redirect_uri),
            ("GOOGLE_OAUTH_SUCCESS_URL", self.google_oauth_success_url),
        ):
            if self._is_local_url(value) or urlparse(value).scheme != "https":
                errors.append(f"{name} must be a non-local HTTPS URL")

        if self.google_signup_enabled:
            if not self.google_client_id.strip() or not self.google_client_secret.strip():
                errors.append("Google OAuth client credentials are required")
            if not self._valid_fernet_key(self.google_token_encryption_key.strip()):
                errors.append("GOOGLE_TOKEN_ENCRYPTION_KEY must be a valid Fernet key")

        if self.course_storage_backend != "s3":
            errors.append("COURSE_STORAGE_BACKEND must be s3")
        if self.allow_legacy_material_writes:
            errors.append("ALLOW_LEGACY_MATERIAL_WRITES must be false; production uploads go directly to S3")
        if self.course_upload_dir.strip() or self.course_mock_file_dir.strip():
            errors.append("Local course material directories must be empty in production")
        if not re.fullmatch(r"(?=.{3,63}$)[a-z0-9][a-z0-9.-]*[a-z0-9]", self.s3_course_materials_bucket):
            errors.append("S3_COURSE_MATERIALS_BUCKET must be a valid bucket name")
        if not self.s3_kms_key_id.strip():
            errors.append("S3_KMS_KEY_ID is required")
        if not self.qdrant_url.strip() or self._is_local_url(self.qdrant_url):
            errors.append("QDRANT_URL must be a non-local service URL")
        if self.qdrant_path.strip() or self.chroma_persist_dir.strip():
            errors.append("Local vector-store paths must be empty in production")
        for name, value in (
            ("SQS_INGESTION_QUEUE_URL", self.sqs_ingestion_queue_url),
            ("SQS_INGESTION_DLQ_URL", self.sqs_ingestion_dlq_url),
            ("SQS_NOTIFICATION_QUEUE_URL", self.sqs_notification_queue_url),
            ("SQS_NOTIFICATION_DLQ_URL", self.sqs_notification_dlq_url),
        ):
            parsed = urlparse(value.strip())
            if parsed.scheme != "https" or not parsed.netloc.endswith("amazonaws.com"):
                errors.append(f"{name} must be an AWS HTTPS queue URL")

        proxy_ranges = [item.strip() for item in self.trusted_proxy_cidrs.split(",") if item.strip()]
        try:
            if not proxy_ranges:
                raise ValueError
            for value in proxy_ranges:
                ipaddress.ip_network(value, strict=False)
        except ValueError:
            errors.append("TRUSTED_PROXY_CIDRS must contain valid CIDR ranges")

        key_path = Path(self.customer_data_key_file)
        try:
            if not key_path.is_file() or len(key_path.read_bytes()) != 64:
                errors.append("CUSTOMER_DATA_KEY_FILE must point to a mounted 64-byte key")
        except OSError:
            errors.append("CUSTOMER_DATA_KEY_FILE cannot be read")

        if errors:
            raise ValueError("Invalid production configuration: " + "; ".join(dict.fromkeys(errors)))


@lru_cache
def get_settings() -> Settings:
    app_env = os.environ.get("APP_ENV", "development").strip().casefold()
    if app_env in {"staging", "production"}:
        # ECS injects values from Secrets Manager/SSM into the process
        # environment. Never let an accidentally copied .env override them.
        return Settings(_env_file=None)
    if app_env == "test":
        candidate = Path(".env.test")
        return Settings(_env_file=candidate if candidate.is_file() else None)
    local = Path(".env.local")
    fallback = Path(".env")
    selected = local if local.is_file() else fallback if fallback.is_file() else None
    settings = Settings(_env_file=selected)
    if settings.app_env in {"staging", "production"} and selected is not None:
        raise ValueError("Deployed APP_ENV must be supplied by the process environment, not an env file")
    return settings
