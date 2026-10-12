"""In-process domain dispatch. This app has no port or public mount."""

from functools import lru_cache

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


@lru_cache(maxsize=1)
def internal_app() -> FastAPI:
    from src.course_source.course_management import router as courses
    from src.course_source.integration_api import require_service_key, service_router
    from src.course_source.schedule_import import router as schedules
    from src.course_source.teacher_management import router as authoring

    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    # Caller is trusted server code; public PaceWise routes independently bind
    # actor/course to the cookie session and enforce CSRF and live enrollment.
    app.dependency_overrides[require_service_key] = lambda: None
    app.include_router(service_router)
    app.include_router(courses)
    app.include_router(schedules)
    app.include_router(authoring)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse({"detail": "Dữ liệu yêu cầu không hợp lệ."}, status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        detail = exc.detail if exc.status_code < 500 else "Nguồn dữ liệu tạm thời chưa sẵn sàng."
        return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=exc.headers)

    return app
