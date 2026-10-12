"""Reverse-proxy and request-size security boundaries."""

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from src.config import Settings
from src.middleware import ProductionSecurityMiddleware


def secured_app() -> FastAPI:
    application = FastAPI()
    application.add_middleware(ProductionSecurityMiddleware)

    @application.post("/echo")
    async def echo(request: Request):
        await request.body()
        return {"ok": True}

    return application


@pytest.mark.asyncio
async def test_untrusted_client_cannot_spoof_forwarded_https(monkeypatch):
    settings = Settings(
        _env_file=None,
        app_env="test",
        force_https=True,
        trusted_proxy_cidrs="10.0.0.0/8",
    )
    monkeypatch.setattr("src.middleware.get_settings", lambda: settings)
    transport = ASGITransport(app=secured_app(), client=("203.0.113.10", 443))
    async with AsyncClient(transport=transport, base_url="http://pacewise.test") as client:
        response = await client.post("/echo", headers={"X-Forwarded-Proto": "https"})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_trusted_proxy_can_report_https_and_receives_hsts(monkeypatch):
    settings = Settings(
        _env_file=None,
        app_env="test",
        force_https=True,
        trusted_proxy_cidrs="10.0.0.0/8",
    )
    monkeypatch.setattr("src.middleware.get_settings", lambda: settings)
    transport = ASGITransport(app=secured_app(), client=("10.0.2.25", 443))
    async with AsyncClient(transport=transport, base_url="http://pacewise.test") as client:
        response = await client.post("/echo", headers={"X-Forwarded-Proto": "https"})

    assert response.status_code == 200
    assert response.headers["strict-transport-security"].startswith("max-age=")


@pytest.mark.asyncio
async def test_oversized_request_is_rejected_before_route_execution(monkeypatch):
    settings = Settings(_env_file=None, app_env="test", max_request_body_mb=1)
    monkeypatch.setattr("src.middleware.get_settings", lambda: settings)
    transport = ASGITransport(app=secured_app())
    async with AsyncClient(transport=transport, base_url="http://pacewise.test") as client:
        response = await client.post("/echo", content=b"x" * (1024 * 1024 + 1))

    assert response.status_code == 413
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_chunked_oversized_request_cannot_bypass_limit(monkeypatch):
    settings = Settings(_env_file=None, app_env="test", max_request_body_mb=1)
    monkeypatch.setattr("src.middleware.get_settings", lambda: settings)

    async def chunks():
        yield b"x" * (700 * 1024)
        yield b"y" * (700 * 1024)

    transport = ASGITransport(app=secured_app())
    async with AsyncClient(transport=transport, base_url="http://pacewise.test") as client:
        response = await client.post("/echo", content=chunks())

    assert response.status_code == 413
    assert response.headers["cache-control"] == "no-store, private"
