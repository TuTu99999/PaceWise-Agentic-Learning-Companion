"""Profile persistence, optimistic concurrency and instructor-only access."""

import pytest
from app import security
from app.main import app
from test_learning_api import _client


@pytest.fixture
def profile_client(monkeypatch):
    previous_factory = security.SessionLocal
    previous_overrides = app.dependency_overrides.copy()
    monkeypatch.setenv("PACEWISE_API_KEY", "profile-test-key")
    client, _factory = _client()
    try:
        yield client
    finally:
        client.close()
        security.SessionLocal = previous_factory
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


PROFILE = "/api/pacewise/v1/teacher/profile"
HEADERS = {"X-PaceWise-Key": "profile-test-key"}


def test_profile_round_trip_and_conflict(profile_client):
    response = profile_client.get(PROFILE, params={"user_id": 1}, headers=HEADERS)
    assert response.status_code == 200
    original = response.json()
    assert original["name"] == "Teacher"
    assert set(original["details"]) == {"title", "department", "office", "office_hours", "bio", "contact_url"}
    payload = {**original["details"], "title": "Lecturer", "department": "Mathematics", "office": "A101",
               "office_hours": "Monday 14:00", "bio": "Discrete mathematics", "contact_url": "https://example.test/teacher",
               "expected_version": original["version"]}
    saved = profile_client.put(PROFILE, params={"user_id": 1}, headers=HEADERS, json=payload)
    assert saved.status_code == 200
    assert saved.json()["details"]["title"] == "Lecturer"
    assert saved.json()["version"] != original["version"]
    assert profile_client.get(PROFILE, params={"user_id": 1}, headers=HEADERS).json() == saved.json()
    assert profile_client.put(PROFILE, params={"user_id": 1}, headers=HEADERS, json=payload).status_code == 409
    payload["expected_version"] = saved.json()["version"]
    payload["title"] = "Senior lecturer"
    assert profile_client.put(PROFILE, params={"user_id": 1}, headers=HEADERS, json=payload).status_code == 200


def test_profile_requires_service_key_and_teacher_enrollment(profile_client):
    assert profile_client.get(PROFILE, params={"user_id": 1}).status_code == 401
    assert profile_client.get(PROFILE, params={"user_id": 2}, headers=HEADERS).status_code == 403
    assert profile_client.put(PROFILE, params={"user_id": 2}, headers=HEADERS, json={}).status_code == 403
    assert profile_client.get(PROFILE, params={"user_id": 999}, headers=HEADERS).status_code == 403


@pytest.mark.parametrize("changes", [{"contact_url": "javascript:alert(1)"}, {"title": "X" * 121}, {"name": "Spoof"}, {"email": "spoof@example.test"}])
def test_profile_rejects_invalid_fields_without_overwriting_saved_data(profile_client, changes):
    original = profile_client.get(PROFILE, params={"user_id": 1}, headers=HEADERS).json()
    result = profile_client.put(PROFILE, params={"user_id": 1}, headers=HEADERS,
                                json={**changes, "expected_version": original["version"]})
    assert result.status_code == 422
    assert profile_client.get(PROFILE, params={"user_id": 1}, headers=HEADERS).json() == original
