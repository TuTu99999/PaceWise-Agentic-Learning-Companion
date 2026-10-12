from __future__ import annotations

import pytest

from src.api import materials as materials_api
from src.config import get_settings
from src.db import SessionLocal
from src.main import app
from src.persistence_models import CourseMaterial
from src.security import SessionContext, get_current_session, require_csrf, require_instructor


@pytest.fixture
def instructor_session(monkeypatch):
    # Existing migration API remains testable only when explicitly enabled.
    monkeypatch.setattr(get_settings(), "allow_legacy_material_writes", True)
    session = SessionContext(
        user_id=91,
        course_id=7,
        course_ids=(7,),
        role="instructor",
        name="Instructor Test",
        email="instructor@example.edu",
        csrf_hash="test",
        sid="instructor-session",
        exp=4_102_444_800,
    )
    app.dependency_overrides[require_instructor] = lambda: session
    app.dependency_overrides[require_csrf] = lambda: session
    app.dependency_overrides[get_current_session] = lambda: session
    with SessionLocal() as db:
        db.query(CourseMaterial).delete()
        db.commit()
    yield session
    app.dependency_overrides.pop(require_instructor, None)
    app.dependency_overrides.pop(require_csrf, None)
    app.dependency_overrides.pop(get_current_session, None)
    with SessionLocal() as db:
        db.query(CourseMaterial).delete()
        db.commit()


@pytest.mark.asyncio
async def test_legacy_upload_disabled_in_normal_deployments(client, instructor_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_legacy_material_writes", False)
    response = await client.post('/api/v1/instructor/materials/upload', data={'course_id': '7'},
                                 files={'file': ('relations.txt', b'relations', 'text/plain')})
    assert response.status_code == 410


@pytest.mark.asyncio
async def test_instructor_can_upload_preview_download_and_delete_material(
    client,
    instructor_session,
    monkeypatch,
):
    monkeypatch.setattr(
        materials_api,
        "index_material_in_qdrant",
        lambda _material, chunks: len(chunks),
    )
    monkeypatch.setattr(materials_api, "delete_material_from_qdrant", lambda *_args: None)

    upload = await client.post(
        "/api/v1/instructor/materials/upload",
        data={"course_id": "7", "title": "Quan hệ hai ngôi", "module_name": "Chương 3"},
        files={"file": ("relations.txt", b"Quan he hai ngoi la tap con cua A x B.", "text/plain")},
    )
    assert upload.status_code == 200
    material_id = upload.json()["material"]["id"]
    assert upload.json()["material"]["chunkCount"] == 1

    listing = await client.get("/api/v1/instructor/materials", params={"course_id": 7})
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [material_id]

    preview = await client.get(f"/api/v1/materials/{material_id}/preview")
    assert preview.status_code == 200
    assert "Quan he hai ngoi" in preview.json()["preview"]

    download = await client.get(f"/api/v1/materials/{material_id}/download")
    assert download.status_code == 200
    assert download.content == b"Quan he hai ngoi la tap con cua A x B."
    assert download.headers["content-disposition"].startswith("attachment;")

    deleted = await client.delete(f"/api/v1/instructor/materials/{material_id}")
    assert deleted.status_code == 200


@pytest.mark.asyncio
async def test_upload_rejects_course_outside_instructor_scope(client, instructor_session):
    response = await client.post(
        "/api/v1/instructor/materials/upload",
        data={"course_id": "8", "title": "Outside course"},
        files={"file": ("notes.txt", b"content", "text/plain")},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_upload_rejects_spoofed_pdf(client, instructor_session):
    response = await client.post(
        "/api/v1/instructor/materials/upload",
        data={"course_id": "7", "title": "Fake PDF"},
        files={"file": ("fake.pdf", b"this is not a pdf", "application/pdf")},
    )
    assert response.status_code == 422
