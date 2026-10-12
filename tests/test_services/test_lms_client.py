import asyncio

import httpx
import pytest
from fastapi import HTTPException

from src.config import Settings
from src.services.lms_client import LMSClient


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_snapshot_creates_one_http_pool_and_drains_requests_before_close(monkeypatch, fail):
    original = httpx.AsyncClient
    constructed, completed = [], []

    async def handler(request):
        assert request.headers["X-PaceWise-Key"] == "service-key"
        if request.url.path == "/bad":
            return httpx.Response(503)
        await asyncio.sleep(0.01)
        completed.append(request.url.path)
        return httpx.Response(200, json={"path": request.url.path})

    def factory(**kwargs):
        client = original(transport=httpx.MockTransport(handler), **kwargs)
        constructed.append(client)
        return client

    monkeypatch.setattr("src.services.lms_client.httpx.AsyncClient", factory)
    service = LMSClient(_settings())
    requests = [("/bad" if fail else "/one", None), ("/two", {"summary": True})]
    if fail:
        with pytest.raises(HTTPException):
            await service.service_get_many(requests)
    else:
        assert await service.service_get_many(requests) == [{"path": "/one"}, {"path": "/two"}]
    assert completed == (["/two"] if fail else ["/one", "/two"])
    assert len(constructed) == 1 and constructed[0].is_closed


def _settings(**overrides) -> Settings:
    values = {
        "lms_base_url": "https://lms.test",
        "pacewise_api_key": "service-key",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.asyncio
async def test_login_launch_flow_uses_server_side_credentials_only():
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/api/session":
            return httpx.Response(200, json={"access_token": "access", "csrf_token": "csrf"})
        if request.url.path == "/api/v1/courses":
            return httpx.Response(200, json=[{"id": 7, "name": "AI"}])
        if request.url.path == "/api/pacewise/launch/7":
            return httpx.Response(200, json={"launch_url": "https://pacewise.test/#/?token=launch-token"})
        if request.url.path == "/api/pacewise/v1/launch/verify":
            return httpx.Response(200, json={"sub": "12", "course_id": 7, "role": "student"})
        if request.url.path == "/api/session" and request.method == "DELETE":
            return httpx.Response(204)
        raise AssertionError(request.url)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://lms.test",
    ) as http_client:
        claims = await LMSClient(_settings(), http_client).login_and_create_launch(
            "student@example.edu", "secret", 7
        )

    assert claims["sub"] == "12"
    assert ("POST", "/api/pacewise/v1/launch/verify") in requests
    assert ("DELETE", "/api/session") in requests


@pytest.mark.asyncio
async def test_lms_client_maps_upstream_failures_to_safe_http_errors():
    async def assert_status(response: httpx.Response, expected: int) -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: response),
            base_url="https://lms.test",
        ) as http_client:
            with pytest.raises(HTTPException) as error:
                await LMSClient(_settings(), http_client).service_get("/resource")
        assert error.value.status_code == expected

    await assert_status(httpx.Response(401, json={"detail": "denied"}), 401)
    await assert_status(httpx.Response(500, json={"detail": "internal"}), 502)


@pytest.mark.asyncio
async def test_lms_client_rejects_missing_service_key():
    client = LMSClient(_settings(pacewise_api_key=""))
    with pytest.raises(HTTPException) as error:
        await client.service_get("/resource")
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_lms_client_rejects_course_outside_enrollment():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/session":
            return httpx.Response(200, json={"access_token": "access", "csrf_token": "csrf"})
        if request.url.path == "/api/v1/courses":
            return httpx.Response(200, json=[{"id": 7}])
        if request.method == "DELETE":
            return httpx.Response(204)
        raise AssertionError(request.url)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://lms.test",
    ) as http_client:
        with pytest.raises(HTTPException) as error:
            await LMSClient(_settings(), http_client).login_and_create_launch(
                "student@example.edu", "secret", 999
            )
    assert error.value.status_code == 403
