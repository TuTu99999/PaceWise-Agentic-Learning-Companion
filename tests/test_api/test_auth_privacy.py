from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_invalid_password_never_echoed_by_validation(client):
    secret = "PRIVATE_PASSWORD_" + "x" * 300
    result = await client.post("/api/v1/auth/lms-login", json={"email": "demo@test.edu", "password": secret})
    assert result.status_code == 422
    assert "PRIVATE_PASSWORD" not in result.text and "input" not in result.text
    assert result.headers["cache-control"] == "no-store, private"
    assert result.headers["referrer-policy"] == "no-referrer"


@pytest.mark.asyncio
async def test_upstream_secrets_not_returned_to_browser(client, monkeypatch, auth_settings):
    monkeypatch.setattr(
        "src.services.lms_client.LMSClient.login_and_create_launch",
        AsyncMock(side_effect=HTTPException(503, "api_key=PRIVATE_SECRET database_password=hidden")),
    )
    result = await client.post("/api/v1/auth/lms-login", json={"email": "demo@test.edu", "password": "test"})
    assert result.status_code == 503
    assert "PRIVATE_SECRET" not in result.text and "database_password" not in result.text


@pytest.mark.asyncio
async def test_lms_bridge_uses_authenticated_identity_and_csrf(client, monkeypatch, auth_settings):
    claims = {
        "iss": "canvas-lms-simulator",
        "aud": "pacewise",
        "sub": "12",
        "course_id": 7,
        "role": "student",
        "name": "Test",
        "email": "test@example.edu",
    }
    monkeypatch.setattr("src.services.lms_client.LMSClient.verify_launch", AsyncMock(return_value=claims))
    monkeypatch.setattr("src.services.lms_client.LMSClient.service_get", AsyncMock(return_value=[{"id": 7}]))
    post = AsyncMock(return_value={"code": "opaque-test-code", "expires_in": 60})
    monkeypatch.setattr("src.services.lms_client.LMSClient.service_post", post)
    assert (await client.post("/api/v1/auth/lms-bridge")).status_code == 401
    await client.post("/api/v1/auth/lms-launch", json={"token": "x" * 40})
    assert (await client.post("/api/v1/auth/lms-bridge")).status_code == 403
    result = await client.post(
        "/api/v1/auth/lms-bridge",
        headers={"X-CSRF-Token": client.cookies["pacewise_csrf"]},
        json={"user_id": 999, "role": "instructor"},
    )
    assert result.status_code == 200
    assert post.call_args.args[1]["user_id"] == 12 and post.call_args.args[1]["role"] == "student"
    assert len(post.call_args.args[1]["session_reference"]) == 64
    assert "email" not in result.json() and "session_reference" not in result.json()
