import ipaddress
import logging
import time
import uuid
from functools import lru_cache

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import get_settings
from src.observability import observe_http

logger = logging.getLogger("pacewise.http")


class RequestBodyTooLargeError(Exception):
    """Internal sentinel; never expose request bytes or parser details."""


def _contains_body_limit_error(exc: BaseException) -> bool:
    if isinstance(exc, RequestBodyTooLargeError):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_contains_body_limit_error(item) for item in exc.exceptions)
    return False


@lru_cache(maxsize=16)
def _proxy_networks(value: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    return tuple(
        ipaddress.ip_network(item.strip(), strict=False)
        for item in value.split(",")
        if item.strip()
    )


def _trusted_proxy(request: Request, configured: str) -> bool:
    if request.client is None:
        return False
    try:
        address = ipaddress.ip_address(request.client.host)
    except ValueError:
        return False
    return any(address in network for network in _proxy_networks(configured))


class ProductionSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        started = time.perf_counter()
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        public_path = request.url.path
        raw_length = request.headers.get("content-length")
        if raw_length:
            try:
                content_length = int(raw_length)
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
            if content_length < 0 or content_length > settings.max_request_body_mb * 1024 * 1024:
                return JSONResponse(
                    {"detail": "Request body is too large"},
                    status_code=413,
                    headers={"Cache-Control": "no-store", "X-Request-ID": request_id},
                )
        maximum_body_bytes = settings.max_request_body_mb * 1024 * 1024
        received_body_bytes = 0
        original_receive = request._receive

        async def receive_limited():
            nonlocal received_body_bytes
            message = await original_receive()
            if message["type"] == "http.request":
                received_body_bytes += len(message.get("body", b""))
                if received_body_bytes > maximum_body_bytes:
                    raise RequestBodyTooLargeError
            return message

        request._receive = receive_limited
        if (settings.private_api_required and public_path.startswith("/api/v1/")
                and not public_path.startswith("/api/v1/private/")
                and public_path not in {
                    "/api/v1/chat/stream",
                    "/api/v1/lms/events/stream",
                    "/api/v1/integrations/google-calendar/callback",
                }
                and not request.scope.get("pacewise.private_dispatch")):
            return JSONResponse({"detail": "Encrypted API transport required"}, status_code=426,
                                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
        forwarded_proto = request.headers.get("x-forwarded-proto", "") if _trusted_proxy(
            request, settings.trusted_proxy_cidrs
        ) else ""
        proto = (forwarded_proto or request.url.scheme).split(",")[0].strip().casefold()
        health_paths = {"/health", "/livez", "/readyz"}
        if settings.force_https and request.url.path not in health_paths and proto != "https":
            return JSONResponse({"detail": "HTTPS is required"}, status_code=400)
        try:
            response = await call_next(request)
        except RequestBodyTooLargeError:
            response = JSONResponse(
                {"detail": "Request body is too large"},
                status_code=413,
                headers={"Cache-Control": "no-store, private"},
            )
        except Exception as exc:
            if _contains_body_limit_error(exc):
                response = JSONResponse(
                    {"detail": "Request body is too large"},
                    status_code=413,
                    headers={"Cache-Control": "no-store, private"},
                )
            else:
                logger.error("request_failed request_id=%s error_type=%s", request_id, type(exc).__name__)
                response = JSONResponse(
                    {"detail": "Không thể xử lý yêu cầu. Hãy thử lại hoặc liên hệ hỗ trợ."},
                    status_code=500,
                )
        duration = time.perf_counter() - started
        route = request.scope.get("route")
        safe_path = getattr(route, "path", "/unmatched")
        if settings.metrics_enabled:
            observe_http(request.method, safe_path, response.status_code, duration)
        logger.info(
            "request_complete method=%s path=%s status=%s duration_ms=%.2f request_id=%s",
            request.method,
            safe_path,
            response.status_code,
            duration * 1000,
            request_id,
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["Pragma"] = "no-cache"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        if proto == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
