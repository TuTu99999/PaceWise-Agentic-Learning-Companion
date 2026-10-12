"""Local HTTP/PostgreSQL smoke. Never prints credentials, cookies, codes, or user data."""

import json
from urllib.parse import parse_qs, urlsplit

import httpx
from private_client import PrivateClient


def check(email, role):
    with (
        PrivateClient(base_url="http://localhost:5173", timeout=20) as pacewise,
        httpx.Client(base_url="http://localhost:8010", timeout=20) as lms,
    ):
        login = pacewise.post("/api/v1/auth/lms-login", json={"email": email, "password": "demo123"})
        assert login.status_code == 200, f"{role}: login status {login.status_code}"
        assert login.json()["user"]["role"] == role
        old_session = pacewise.cookies["pacewise_session"]
        csrf = {"X-CSRF-Token": pacewise.cookies["pacewise_csrf"]}
        bridge = pacewise.post("/api/v1/auth/lms-bridge", headers=csrf)
        assert bridge.status_code == 200, f"{role}: bridge status {bridge.status_code}"
        code = bridge.json()["code"]
        entered = lms.post(
            "/api/pacewise/sso/consume",
            data={"code": code},
            headers={"Origin": "http://localhost:5173", "Accept": "application/json"},
            follow_redirects=False,
        )
        assert entered.status_code == 200, f"{role}: consume status {entered.status_code}"
        assert entered.json() == {"redirect": "/"}
        assert entered.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert entered.headers["access-control-allow-credentials"] == "true"
        assert lms.get("/api/session/me").json()["user"]["role"] == role
        replay = lms.post("/api/pacewise/sso/consume", data={"code": code}, headers={"Origin": "http://localhost:5173"})
        assert replay.status_code == 401
        course = login.json()["user"]["courseId"]
        launch = lms.post(f"/api/pacewise/launch/{course}", headers={"X-CSRF-Token": lms.cookies["canvas_csrf"]})
        assert launch.status_code == 200
        url = urlsplit(launch.json()["launch_url"])
        token = parse_qs(url.fragment.partition("?")[2])["token"][0]
        assert url.path == "/app" and not url.query and "." not in token and "@" not in token
        returned = pacewise.post("/api/v1/auth/lms-launch", json={"token": token})
        assert returned.status_code == 200
        assert pacewise.cookies["pacewise_session"] == old_session
        logout = pacewise.post("/api/v1/auth/logout", headers=csrf)
        assert logout.status_code == 200 and logout.json()["linkedLmsRevoked"]
        assert lms.get("/api/session/me").status_code == 401
        assert pacewise.get("/api/v1/auth/me", headers={"Cookie": f"pacewise_session={old_session}"}).status_code == 401
        return {
            "role": role,
            "login": 200,
            "bridge": 200,
            "code_replay": 401,
            "return_to_pacewise": 200,
            "logout": 200,
            "old_session_replay": 401,
            "linked_lms_after_logout": 401,
            "identity_in_url": False,
        }


if __name__ == "__main__":
    print(json.dumps([check("student@canvas.local", "student"), check("teacher@canvas.local", "instructor")], indent=2))
