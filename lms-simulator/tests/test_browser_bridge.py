from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from app.models import BrowserBridgeTicket, Enrollment
from sqlalchemy import select
from test_pacewise_contracts import env as contract_env

# Register the shared isolated-database fixture without shadowing an import.
env = contract_env


def issue(client, headers, user_id=2, role="student", reference="a" * 64):
    return client.post(
        "/api/pacewise/v1/browser-bridge",
        headers=headers,
        json={"user_id": user_id, "course_id": 1, "role": role, "session_reference": reference},
    )


def consume(client, code, origin="http://localhost:5173"):
    return client.post(
        "/api/pacewise/sso/consume", data={"code": code}, headers={"Origin": origin}, follow_redirects=False
    )


@pytest.mark.parametrize("user_id,role", [(1, "instructor"), (2, "student")])
def test_two_way_opaque_bridge_and_revocation(env, monkeypatch, user_id, role):
    client, _, _, _, headers = env
    monkeypatch.setenv("PACEWISE_URL", "http://localhost:5173")
    result = issue(client, headers, user_id, role)
    assert result.status_code == 200
    code = result.json()["code"]
    assert "@" not in code and "." not in code and "user" not in result.json()
    entered = consume(client, code)
    assert entered.status_code == 303 and entered.headers["location"] == "/"
    assert any(
        "canvas_session=" in cookie and "HttpOnly" in cookie for cookie in entered.headers.get_list("set-cookie")
    )
    assert client.get("/api/session/me").json()["user"]["id"] == user_id
    assert consume(client, code).status_code == 401
    launch = client.post("/api/pacewise/launch/1", headers={"X-CSRF-Token": client.cookies["canvas_csrf"]})
    url = urlsplit(launch.json()["launch_url"])
    assert url.path == "/app" and not url.query
    token = parse_qs(url.fragment.partition("?")[2])["token"][0]
    assert "." not in token and "@" not in token
    verified = client.post("/api/pacewise/v1/launch/verify", headers=headers, json={"token": token})
    assert verified.json()["role"] == role
    assert client.post("/api/pacewise/v1/launch/verify", headers=headers, json={"token": token}).status_code == 401
    client.post(
        "/api/pacewise/v1/browser-bridge/revoke",
        headers=headers,
        json={"user_id": user_id, "session_reference": "a" * 64},
    )
    assert client.get("/api/session/me").status_code == 401


def test_bridge_denies_bad_origin_expiry_role_change_and_missing_key(env, monkeypatch):
    client, factory, _, _, headers = env
    monkeypatch.setenv("PACEWISE_URL", "http://localhost:5173")
    assert issue(client, {}).status_code == 401
    assert issue(client, headers, role="instructor").status_code == 403
    code = issue(client, headers).json()["code"]
    assert consume(client, code, "https://attacker.invalid").status_code == 403
    with factory() as db:
        ticket = db.scalar(select(BrowserBridgeTicket))
        ticket.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert consume(client, code).status_code == 401
    code = issue(client, headers).json()["code"]
    with factory() as db:
        db.scalar(select(Enrollment).where(Enrollment.user_id == 2, Enrollment.course_id == 1)).role = "instructor"
        db.commit()
    assert consume(client, code).status_code == 403


def test_browser_login_no_bearer_token_csrf_cannot_be_bypassed_logout_replay(env):
    client, _, _, _, _ = env
    login = client.post("/api/session", json={"email": "student@example.test", "password": "demo12345"})
    assert login.status_code == 200
    assert "access_token" not in login.json() and "password" not in login.text
    old = client.cookies["canvas_session"]
    assert client.delete("/api/session", headers={"Authorization": "junk"}).status_code == 403
    assert client.delete("/api/session", headers={"X-CSRF-Token": client.cookies["canvas_csrf"]}).status_code == 200
    assert client.get("/api/session/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401


@pytest.mark.parametrize("user_id,role", [(1, "instructor"), (2, "student")])
def test_credentialed_cors_bridge_json_acknowledgement(env, monkeypatch, user_id, role):
    client, _, _, _, headers = env
    monkeypatch.setenv("PACEWISE_URL", "http://localhost:5173/app")
    code = issue(client, headers, user_id, role).json()["code"]
    entered = client.post(
        "/api/pacewise/sso/consume",
        data={"code": code},
        headers={"Origin": "http://localhost:5173", "Accept": "application/json"},
        follow_redirects=False,
    )
    assert entered.status_code == 200
    assert entered.json() == {"redirect": "/"}
    assert "location" not in entered.headers
    assert entered.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert entered.headers["access-control-allow-credentials"] == "true"
    assert "Origin" in entered.headers["vary"]
    assert "no-store" in entered.headers["cache-control"]
    assert any("HttpOnly" in cookie for cookie in entered.headers.get_list("set-cookie"))
    assert client.get("/api/session/me").json()["user"]["role"] == role
    assert consume(client, code).status_code == 401


@pytest.mark.parametrize("origin", [None, "null", "https://attacker.invalid", "http://127.0.0.1:5173"])
def test_cors_bridge_rejects_untrusted_origins_without_consuming_ticket(env, monkeypatch, origin):
    client, _, _, _, headers = env
    monkeypatch.setenv("PACEWISE_URL", "http://localhost:5173")
    code = issue(client, headers).json()["code"]
    response = client.post(
        "/api/pacewise/sso/consume", data={"code": code},
        headers={"Accept": "application/json", **({"Origin": origin} if origin else {})},
    )
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers
    assert consume(client, code).status_code == 303


def test_bridge_preflight_allows_only_configured_origin(env):
    client, *_ = env
    for origin, expected_status in [("http://localhost:5173", 200), ("https://attacker.invalid", 400), ("null", 400)]:
        response = client.options(
            "/api/pacewise/sso/consume",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
        )
        assert response.status_code == expected_status
        assert ("access-control-allow-origin" in response.headers) == (expected_status == 200)
