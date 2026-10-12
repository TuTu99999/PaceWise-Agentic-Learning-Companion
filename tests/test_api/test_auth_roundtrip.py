from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_return_launch_keeps_authenticated_session_link(client, monkeypatch, auth_settings):
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
    monkeypatch.setattr(
        "src.services.lms_client.LMSClient.service_get",
        AsyncMock(return_value=[{"id": 7, "enrollment_role": "student"}, {"id": 8, "enrollment_role": "instructor"}]),
    )
    assert (await client.post("/api/v1/auth/lms-launch", json={"token": "x" * 40})).status_code == 200
    cookie = client.cookies["pacewise_session"]
    csrf = client.cookies["pacewise_csrf"]
    response = await client.post("/api/v1/auth/lms-launch", json={"token": "y" * 40})
    assert response.status_code == 200
    assert client.cookies["pacewise_session"] == cookie and client.cookies["pacewise_csrf"] == csrf
    assert response.json()["user"]["courseIds"] == ["7"]


@pytest.mark.asyncio
async def test_other_identity_does_not_reuse_session(client, monkeypatch, auth_settings):
    claims = {
        "iss": "canvas-lms-simulator",
        "aud": "pacewise",
        "sub": "12",
        "course_id": 7,
        "role": "student",
        "name": "Test",
        "email": "test@example.edu",
    }
    verify = AsyncMock(side_effect=[claims, {**claims, "sub": "13"}])
    monkeypatch.setattr("src.services.lms_client.LMSClient.verify_launch", verify)
    monkeypatch.setattr("src.services.lms_client.LMSClient.service_get", AsyncMock(return_value=[{"id": 7}]))
    await client.post("/api/v1/auth/lms-launch", json={"token": "x" * 40})
    old = client.cookies["pacewise_session"]
    response = await client.post("/api/v1/auth/lms-launch", json={"token": "y" * 40})
    assert response.status_code == 200 and response.json()["user"]["id"] == "13"
    assert client.cookies["pacewise_session"] != old
