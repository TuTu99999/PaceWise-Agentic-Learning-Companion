from collections.abc import Generator

from app import account_api, security
from app.db import Base, get_db
from app.main import app
from app.models import User
from app.security import hash_password
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def _test_client(tmp_path) -> tuple[TestClient, sessionmaker]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with factory() as db:
        db.add_all(
            [
                User(
                    email="student@example.test",
                    full_name="Test Student",
                    password_hash=hash_password("demo12345"),
                    role="student",
                    avatar_color="#2563eb",
                ),
                User(
                    email="other@example.test",
                    full_name="Other Student",
                    password_hash=hash_password("demo12345"),
                    role="student",
                    avatar_color="#0b874b",
                ),
            ]
        )
        db.commit()

    def override_db() -> Generator[Session, None, None]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    security.SessionLocal = factory
    account_api.ACCOUNT_UPLOAD_DIR = tmp_path
    return TestClient(app), factory


def _login(
    client: TestClient,
    email: str = "student@example.test",
    password: str = "demo12345",
) -> dict[str, str]:
    response = client.post("/api/session", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {client.cookies['canvas_session']}"}


def test_account_profile_notifications_and_password(tmp_path) -> None:
    client, _ = _test_client(tmp_path)
    headers = _login(client)

    account = client.get("/api/account", headers=headers)
    assert account.status_code == 200
    assert account.json()["profile"]["display_name"] == "Test Student"
    assert set(account.json()["notifications"]) == {
        "course_activities",
        "discussions",
        "conversations",
        "scheduling",
    }

    updated = client.put(
        "/api/account/profile",
        headers=headers,
        json={
            "full_name": "Student Updated",
            "display_name": "Stu",
            "pronouns": "they/them",
            "bio": "Learning every day.",
            "timezone": "UTC",
            "language": "vi",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["user"]["name"] == "Student Updated"
    assert updated.json()["profile"]["bio"] == "Learning every day."
    assert updated.json()["profile"]["language"] == "vi"

    notification_update = client.put(
        "/api/account/notifications",
        headers=headers,
        json={
            "preferences": {
                "course_activities": "immediately",
                "discussions": "daily",
                "conversations": "weekly",
                "scheduling": "off",
            }
        },
    )
    assert notification_update.status_code == 200
    assert notification_update.json()["notifications"]["scheduling"] == "off"

    password = client.put(
        "/api/account/password",
        headers=headers,
        json={"current_password": "demo12345", "new_password": "new-password-123"},
    )
    assert password.status_code == 200
    assert _login(client, "student@example.test", "new-password-123")


def test_personal_files_are_private(tmp_path) -> None:
    client, _ = _test_client(tmp_path)
    owner_headers = _login(client)
    other_headers = _login(client, "other@example.test")

    upload = client.post(
        "/api/account/files",
        headers=owner_headers,
        files={"upload": ("notes.txt", b"private notes", "text/plain")},
    )
    assert upload.status_code == 201
    file_id = upload.json()["id"]

    owner_download = client.get(f"/api/account/files/{file_id}/download", headers=owner_headers)
    assert owner_download.status_code == 200
    assert owner_download.content == b"private notes"

    other_download = client.get(f"/api/account/files/{file_id}/download", headers=other_headers)
    assert other_download.status_code == 404

    deleted = client.delete(f"/api/account/files/{file_id}", headers=owner_headers)
    assert deleted.status_code == 200
    assert not list(tmp_path.iterdir())
