import pytest
from test_pacewise_contracts import env as contract_env

env = contract_env


@pytest.mark.parametrize("path", ["/", "/courses/1", "/static/app.js", "/docs", "/openapi.json"])
def test_api_only_mode_does_not_serve_web_or_docs(env, monkeypatch, path):
    monkeypatch.setenv("LMS_WEB_ENABLED", "false")
    client, *_ = env
    response = client.get(path)
    assert response.status_code == 404
    assert response.json() == {"detail": "LMS web is disabled"}


def test_api_only_mode_keeps_health_login_course_access_and_service_auth(env, monkeypatch):
    monkeypatch.setenv("LMS_WEB_ENABLED", "false")
    client, _, _, _, headers = env
    assert client.get("/api/health").status_code == 200
    login = client.post("/api/session", headers=headers,
                        json={"email": "student@example.test", "password": "demo12345"})
    assert login.status_code == 200
    assert "access_token" in login.json()  # Only authenticated service callers receive it.
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/courses", headers=auth).status_code == 200
    assert client.get("/api/pacewise/v1/courses/1/assignments?user_id=2", headers=headers).status_code == 200
    assert client.get("/api/pacewise/v1/courses/1/assignments?user_id=2").status_code == 401


def test_web_can_be_reenabled_without_changing_api_routes(env, monkeypatch):
    monkeypatch.setenv("LMS_WEB_ENABLED", "true")
    client, *_ = env
    assert client.get("/").status_code == 200
