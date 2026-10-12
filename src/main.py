import asyncio
import hmac
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select

from src.agents.graph import runtime_agent
from src.agents.tools.qdrant_retriever import warm_rag_models
from src.api.adaptive_assessment import router as adaptive_assessment_router
from src.api.calendar_export import router as calendar_export_router
from src.api.course_membership import router as course_membership_router
from src.api.course_uploads import router as course_uploads_router
from src.api.google_calendar import router as google_calendar_router
from src.api.google_signup import router as google_signup_router
from src.api.instructor_management import router as instructor_management_router
from src.api.lms_files import router as lms_files_router
from src.api.lms_integration import router as lms_router
from src.api.materials import router as materials_router
from src.api.notifications import router as notifications_router
from src.api.private_api import router as private_api_router
from src.api.realtime import LmsEventBroker
from src.api.realtime import router as realtime_router
from src.api.routes import router
from src.api.study_sessions import router as study_sessions_router
from src.api.workspace import router as workspace_router
from src.config import get_settings
from src.db import SessionLocal, initialize_database
from src.middleware import ProductionSecurityMiddleware
from src.observability import render_prometheus
from src.persistence_models import WorkerHeartbeat
from src.readiness import readiness_report

settings = get_settings()
is_deployed = settings.app_env in {"staging", "production"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    initialize_database()
    if settings.course_source_mode == "standalone":
        from src.course_source.db import initialize_database as initialize_course_source
        from src.course_source.gateway import internal_app

        initialize_course_source()
        # Pay router import/validation cost during startup, not when the first
        # instructor opens an aggregate dashboard.
        internal_app()
    if settings.rag_warm_on_startup and settings.app_env != "test":
        # Move ONNX initialization to application readiness instead of making
        # the first student's question pay the cold-start cost.
        await asyncio.to_thread(warm_rag_models)
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    event_broker = LmsEventBroker(settings)
    await event_broker.start()
    app.state.lms_event_broker = event_broker
    try:
        async with runtime_agent(settings) as durable_agent:
            app.state.agent = durable_agent
            yield
    finally:
        await event_broker.stop()
        print("Shutting down...")


app = FastAPI(
    title="AI20K Agent",
    description="AI Agent built with LangGraph",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if is_deployed else "/docs",
    redoc_url=None if is_deployed else "/redoc",
    openapi_url=None if is_deployed else "/openapi.json",
)


@app.exception_handler(RequestValidationError)
async def safe_validation_error(request: Request, exc: RequestValidationError):
    # Pydantic's default errors include rejected input, including passwords.
    return JSONResponse(status_code=422, content={"detail": "Dữ liệu yêu cầu không hợp lệ."})


@app.exception_handler(HTTPException)
async def safe_http_error(request: Request, exc: HTTPException):
    detail = exc.detail if exc.status_code < 500 else "Dịch vụ tạm thời chưa sẵn sàng. Vui lòng thử lại."
    partial = (exc.headers or {}).get("X-PaceWise-Partial-Created", "")
    if exc.status_code == 502 and partial.isdigit() and int(partial) <= 500:
        detail = f"Created {int(partial)} event(s) before Google Calendar failed. Please retry."
    return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=exc.headers)

app.add_middleware(ProductionSecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(adaptive_assessment_router, prefix="/api/v1")
app.include_router(lms_router, prefix="/api/v1")
app.include_router(workspace_router, prefix="/api/v1")
app.include_router(study_sessions_router, prefix="/api/v1")
app.include_router(google_calendar_router, prefix="/api/v1")
app.include_router(google_signup_router, prefix="/api/v1")
app.include_router(calendar_export_router, prefix="/api/v1")
app.include_router(realtime_router, prefix="/api/v1")
app.include_router(materials_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(lms_files_router, prefix="/api/v1")
app.include_router(course_uploads_router, prefix="/api/v1")
app.include_router(course_membership_router, prefix="/api/v1")
app.include_router(instructor_management_router, prefix="/api/v1")
app.include_router(private_api_router, prefix="/api/v1")


@app.get("/health")
async def health():
    """Backward-compatible liveness endpoint for local tooling."""
    checkpoint = "postgres" if settings.use_postgres_checkpoint and settings.database_url.startswith("postgresql") else "memory"
    return {"status": "ok", "env": settings.app_env, "checkpoint": checkpoint}


@app.get("/livez", include_in_schema=False)
async def livez():
    return {"status": "alive"}


@app.get("/readyz", include_in_schema=False)
def readyz():
    healthy, checks = readiness_report(settings)
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ready" if healthy else "not_ready", "checks": checks},
    )


@app.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
async def metrics(request: Request):
    if is_deployed:
        expected = settings.metrics_bearer_token
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not expected or not hmac.compare_digest(supplied, expected):
            raise HTTPException(401, "Metrics authorization required")
    return render_prometheus()


@app.get("/workerz", include_in_schema=False)
def worker_health(request: Request):
    if is_deployed:
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not settings.metrics_bearer_token or not hmac.compare_digest(supplied, settings.metrics_bearer_token):
            raise HTTPException(401, "Worker health authorization required")
    with SessionLocal() as db:
        row = db.scalar(select(WorkerHeartbeat).order_by(WorkerHeartbeat.heartbeat_at.desc()).limit(1))
    stale_after = timedelta(seconds=max(60, settings.lms_sync_interval_seconds * 3))
    heartbeat = None if row is None else (
        row.heartbeat_at.replace(tzinfo=UTC) if row.heartbeat_at.tzinfo is None else row.heartbeat_at.astimezone(UTC)
    )
    healthy = heartbeat is not None and datetime.now(UTC) - heartbeat <= stale_after
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "healthy" if healthy else "stale",
            "worker": None if row is None else {
                "kind": row.worker_kind,
                "queueLag": row.queue_lag,
                "failedJobs": row.failed_jobs,
                "heartbeatAt": heartbeat.isoformat(),
            },
        },
    )
