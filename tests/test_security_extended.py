import hashlib
import json
import time

import pytest
from fastapi import HTTPException, Request

from src import security
from src.api.workspace import WorkspaceRequest, save_workspace
from src.config import Settings
from src.db import SessionLocal
from src.persistence_models import PaceWiseSession, UserWorkspace


def _settings(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "pacewise_session_secret": "test-session-secret-with-at-least-32-characters",
        **overrides,
    }
    return Settings(_env_file=None, **values)


def _claims(role: str = "student") -> dict:
    return {
        "sub": "812",
        "course_id": 703,
        "role": role,
        "name": "Security Test",
        "email": "security@example.edu",
    }


def _request(*, cookie: str = "", csrf_header: str = "") -> Request:
    headers = []
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    if csrf_header:
        headers.append((b"x-csrf-token", csrf_header.encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def _signed_token(payload: dict, settings: Settings) -> str:
    encoded = security._b64encode(json.dumps(payload).encode())
    return f"{encoded}.{security._sign(encoded, settings)}"


def test_session_configuration_and_role_are_rejected_early():
    with pytest.raises(HTTPException) as weak:
        security._secret(_settings(pacewise_session_secret="short"))
    assert weak.value.status_code == 503

    with SessionLocal() as db, pytest.raises(HTTPException) as unsupported:
        security.issue_session(db, _claims("admin"), _settings())
    assert unsupported.value.status_code == 403


def test_session_decode_rejects_tampering_audience_expiry_and_hash_mismatch():
    settings = _settings()
    now = int(time.time())
    with SessionLocal() as db:
        token, _csrf = security.issue_session(db, _claims(), settings, course_ids=[701])
        context = security.decode_session(token, settings, db)
        assert context.course_ids == (701, 703)

        with pytest.raises(HTTPException):
            security.decode_session(f"{token}tampered", settings, db)

        bad_audience = _signed_token(
            {
                "iss": "pacewise-api",
                "aud": "wrong-web",
                "sid": context.sid,
                "exp": now + 60,
            },
            settings,
        )
        with pytest.raises(HTTPException):
            security.decode_session(bad_audience, settings, db)

        expired = _signed_token(
            {
                "iss": "pacewise-api",
                "aud": "pacewise-web",
                "sid": context.sid,
                "exp": now - 1,
            },
            settings,
        )
        with pytest.raises(HTTPException):
            security.decode_session(expired, settings, db)

        row = db.get(PaceWiseSession, context.sid)
        row.token_hash = hashlib.sha256(f"mismatch:{context.sid}".encode()).hexdigest()
        db.commit()
        with pytest.raises(HTTPException):
            security.decode_session(token, settings, db)


def test_detached_session_authorization_helpers_and_debug_payload():
    settings = _settings()
    with pytest.raises(HTTPException, match="Authentication required"):
        security.get_detached_session(_request(), settings)

    with SessionLocal() as db:
        token, csrf = security.issue_session(db, _claims(), settings)
    request = _request(
        cookie=(
            f"{settings.pacewise_session_cookie}={token}; "
            f"{settings.pacewise_csrf_cookie}={csrf}"
        ),
        csrf_header=csrf,
    )
    context = security.get_detached_session(request, settings)
    assert context.user_id == 812
    assert security.require_csrf(request, context, settings) is context

    with pytest.raises(HTTPException, match="Instructor"):
        security.require_instructor(context)
    with pytest.raises(HTTPException, match="CSRF"):
        security.require_csrf(_request(cookie=f"{settings.pacewise_csrf_cookie}=wrong", csrf_header="wrong"), context, settings)

    debug = security.session_debug_payload(context)
    assert debug["user_id"] == 812
    assert "csrf_hash" not in debug


def test_new_workspace_row_is_created_server_side():
    session = security.SessionContext(
        user_id=98_712,
        course_id=703,
        course_ids=(703,),
        role="student",
        name="Workspace Test",
        email="workspace@example.edu",
        csrf_hash="hash",
        sid="workspace-sid",
        exp=4_102_444_800,
    )
    with SessionLocal() as db:
        db.query(UserWorkspace).filter(UserWorkspace.user_id == session.user_id).delete()
        db.commit()
        result = save_workspace(
            WorkspaceRequest(state={"plan": {"id": "new-plan"}}),
            session,
            db,
        )
        row = db.get(UserWorkspace, session.user_id)

    assert result["version"] == 1
    assert json.loads(row.state_json)["plan"]["id"] == "new-plan"
