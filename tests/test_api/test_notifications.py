import base64
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from src.config import Settings, get_settings
from src.db import SessionLocal
from src.main import app
from src.persistence_models import NotificationDailyBudget, NotificationJob, UserWorkspace, WebPushSubscription


@pytest.fixture(autouse=True)
def isolation(tmp_path):
    settings = Settings(
        _env_file=None,
        app_env="test",
        pacewise_api_key="test-service-key",
        pacewise_session_secret="a-test-session-secret-longer-than-32-characters",
        webpush_private_key_file=str(tmp_path / "vapid.pem"),
    )
    app.dependency_overrides[get_settings] = lambda: settings
    with SessionLocal() as db:
        for model in (NotificationJob, NotificationDailyBudget, WebPushSubscription):
            db.query(model).delete()
        db.query(UserWorkspace).filter(UserWorkspace.user_id.in_([42, 43])).delete()
        db.commit()
    yield
    app.dependency_overrides.pop(get_settings, None)


async def login(client, monkeypatch, role="student"):
    monkeypatch.setattr(
        "src.services.lms_client.LMSClient.verify_launch",
        AsyncMock(
            return_value={
                "iss": "canvas-lms-simulator",
                "aud": "pacewise",
                "sub": "42",
                "course_id": 7,
                "role": role,
                "name": "Student",
                "email": "student@example.edu",
            }
        ),
    )
    monkeypatch.setattr("src.services.lms_client.LMSClient.service_get", AsyncMock(return_value=[{"id": 7}]))
    response = await client.post("/api/v1/auth/lms-launch", json={"token": "x" * 40})
    assert response.status_code == 200
    return {"X-CSRF-Token": client.cookies["pacewise_csrf"]}


def subscription():
    public = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    )
    return {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test",
        "keys": {
            "p256dh": base64.urlsafe_b64encode(public).decode().rstrip("="),
            "auth": base64.urlsafe_b64encode(b"0123456789abcdef").decode().rstrip("="),
        },
    }


@pytest.mark.asyncio
async def test_student_subscription_is_idempotent_csrf_protected_and_revoked_on_logout(client, monkeypatch):
    headers = await login(client, monkeypatch)
    payload = subscription()
    assert (await client.post("/api/v1/notifications/push", json=payload)).status_code == 403
    for _ in range(2):
        assert (await client.post("/api/v1/notifications/push", headers=headers, json=payload)).status_code == 200
    status = await client.get("/api/v1/notifications/push")
    assert status.json()["subscribed"] is True
    assert "PRIVATE" not in status.text and payload["endpoint"] not in status.text
    with SessionLocal() as db:
        assert db.query(WebPushSubscription).count() == 1
    assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 200
    with SessionLocal() as db:
        assert db.query(WebPushSubscription).count() == 0


@pytest.mark.asyncio
async def test_teacher_cannot_register_push(client, monkeypatch):
    headers = await login(client, monkeypatch, "instructor")
    assert (await client.post("/api/v1/notifications/push", headers=headers, json=subscription())).status_code == 403


@pytest.mark.asyncio
async def test_endpoint_cannot_be_rebound_to_another_student(client, monkeypatch):
    headers = await login(client, monkeypatch)
    payload = subscription()
    import hashlib

    with SessionLocal() as db:
        db.add(
            WebPushSubscription(
                id=hashlib.sha256(payload["endpoint"].encode()).hexdigest(),
                user_id=43,
                session_id="another-session",
                subscription_json=json.dumps(payload),
            )
        )
        db.commit()
    assert (await client.post("/api/v1/notifications/push", headers=headers, json=payload)).status_code == 409


@pytest.mark.asyncio
async def test_claim_receipt_is_user_scoped_and_counts_once(client, monkeypatch):
    headers = await login(client, monkeypatch)
    now = datetime.now(UTC)
    with SessionLocal() as db:
        db.add(
            UserWorkspace(user_id=42, state_json=json.dumps({"reminders": {"preferences": {"browserEnabled": True}}}))
        )
        for user_id, key in [(42, "ours"), (43, "theirs")]:
            db.add(
                NotificationJob(
                    id=key,
                    user_id=user_id,
                    reminder_key=key,
                    kind="study_block",
                    scheduled_at=now - timedelta(minutes=1),
                    expires_at=now + timedelta(minutes=15),
                    payload_json="{}",
                )
            )
        db.commit()
    path = "/api/v1/notifications/claim"
    assert (await client.post(path, headers=headers, json={"ids": ["ours", "theirs"]})).json() == {"ids": ["ours"]}
    assert (await client.post(path, headers=headers, json={"ids": ["ours"]})).json() == {"ids": []}
    with SessionLocal() as db:
        assert db.get(NotificationJob, "theirs").status == "pending"
        assert db.query(NotificationDailyBudget).one().count == 1


@pytest.mark.asyncio
async def test_workspace_preferences_persist_and_schedule_reflect_without_ai_content(client, monkeypatch):
    headers = await login(client, monkeypatch)
    value = {
        "studyPreferences": {"sessionMinutes": 25, "breakMinutes": 5},
        "reminders": {"preferences": {"quietHoursEnabled": True, "quietStart": "22:00", "quietEnd": "07:00"}},
        "sessions": [
            {"id": "s1", "taskId": "t1", "completedAt": datetime.now(UTC).isoformat(), "note": "PRIVATE_NOTE"}
        ],
    }
    response = await client.put("/api/v1/workspace", headers=headers, json={"state": value})
    assert response.status_code == 200, response.text
    saved = (await client.get("/api/v1/workspace")).json()["state"]
    assert saved["studyPreferences"] == {**value["studyPreferences"], "checkpointMinutes": 0, "adaptiveSuggestionsEnabled": True, "activityRhythms": []}
    # Student-selected course rhythms cannot target someone else's course.
    unauthorized = {"studyPreferences": {"activityRhythms": [{"courseId": 99999, "activityType": "concept",
        "sessionMinutes": 30, "breakMinutes": 5}]}}
    assert (await client.put("/api/v1/workspace", headers=headers, json={"state": unauthorized})).status_code == 403
    assert saved["reminders"]["preferences"]["quietHoursEnabled"] is True
    with SessionLocal() as db:
        job = db.query(NotificationJob).filter(NotificationJob.kind == "reflect_session").one()
        assert "PRIVATE_NOTE" not in job.payload_json
    for patch in [{"sessionMinutes": 500, "breakMinutes": 5}, {"sessionMinutes": 25, "breakMinutes": -1}]:
        rejected = await client.put("/api/v1/workspace", headers=headers, json={"state": {"studyPreferences": patch}})
        assert rejected.status_code == 422


@pytest.mark.asyncio
async def test_bad_notification_source_is_rejected_without_partial_workspace_save(client, monkeypatch):
    headers = await login(client, monkeypatch)
    response = await client.put("/api/v1/workspace", headers=headers, json={"state": {"sessions": ["invalid"]}})
    assert response.status_code == 422
