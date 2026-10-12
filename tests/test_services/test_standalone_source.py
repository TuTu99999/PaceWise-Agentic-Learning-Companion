"""Standalone regression: real domain DB, no simulator or outgoing HTTP."""

import base64
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import delete, select

from src.config import get_settings
from src.course_source.db import Base, engine, initialize_database
from src.course_source.db import SessionLocal as CourseSession
from src.course_source.migration import export_snapshot, import_snapshot
from src.course_source.models import Course, Enrollment, User
from src.db import SessionLocal
from src.db import get_db as pacewise_get_db
from src.main import app
from src.services.lms_client import LMSClient


def test_native_upload_accepts_production_object_storage_backend(auth_settings):
    from src.api.course_uploads import native_instructor

    settings = auth_settings.model_copy(
        update={"course_source_mode": "standalone", "course_storage_backend": "s3"}
    )

    native_instructor(type("Session", (), {"role": "instructor"})(), settings)


def password_hash(password):
    salt = b"test-preserved!!"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return base64.urlsafe_b64encode(salt).decode() + ":" + base64.urlsafe_b64encode(digest).decode()


@pytest.fixture
def native(auth_settings, monkeypatch, tmp_path):
    assert engine.dialect.name == "sqlite", "Never mutate a real source database in tests"
    initialize_database()
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(delete(table))
    with CourseSession() as db:
        db.add_all([User(id=1, email="teacher@native.test", full_name="Preserved teacher", role="instructor", password_hash=password_hash("native-test")),
                    User(id=2, email="student@native.test", full_name="Preserved student", role="student", password_hash=password_hash("native-test")),
                    User(id=3, email="other@native.test", full_name="Other student", role="student", password_hash=password_hash("native-test")),
                    User(id=4, email="other-teacher@native.test", full_name="Other teacher", role="instructor", password_hash=password_hash("native-test")),
                    User(id=5, email="empty-student@native.test", full_name="Student without course", role="student", password_hash=password_hash("native-test")),
                    User(id=6, email="empty-teacher@native.test", full_name="Teacher without course", role="instructor", password_hash=password_hash("native-test")),
                    Course(id=1, code="N101", name="Native course", term="Demo", color="#2563eb"),
                    Course(id=2, code="N102", name="Other course", term="Demo", color="#2563eb")])
        db.flush()
        db.add_all([Enrollment(user_id=1, course_id=1, role="instructor"), Enrollment(user_id=2, course_id=1, role="student"),
                    Enrollment(user_id=3, course_id=2, role="student"), Enrollment(user_id=4, course_id=2, role="instructor")])
        db.commit()
    settings = auth_settings.model_copy(update={"course_source_mode": "standalone", "course_upload_dir": str(tmp_path / "uploads")})
    from src.api.course_uploads import CourseUploadReceipt, CourseUploadTicket
    from src.persistence_models import LmsFileIndex

    with SessionLocal() as db:
        db.query(LmsFileIndex).delete()
        db.query(CourseUploadReceipt).delete()
        db.query(CourseUploadTicket).delete()
        db.commit()
    from src.course_source import uploads

    monkeypatch.setattr(uploads, "UPLOAD_DIR", tmp_path / "uploads")
    app.dependency_overrides[get_settings] = lambda: settings

    async def no_network(*args, **kwargs):
        raise AssertionError("Standalone made an outgoing HTTP request")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_network)
    yield settings


async def sign_in(client, email="teacher@native.test"):
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "native-test"})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": client.cookies["pacewise_csrf"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("email", "role"),
    [
        ("empty-student@native.test", "student"),
        ("empty-teacher@native.test", "instructor"),
    ],
)
async def test_native_login_allows_both_roles_without_an_active_course(client, native, email, role):
    headers = await sign_in(client, email)
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    user = me.json()["user"]
    assert user["role"] == role
    assert user["courseId"] == "0"
    assert user["courseIds"] == []

    synchronized = await client.get("/api/v1/lms/sync", headers=headers)
    assert synchronized.status_code == 200
    assert synchronized.json()["courses"] == []
    assert synchronized.json()["tasks"] == []
    assert synchronized.json()["activeCourseId"] is None
    if role == "instructor":
        overview = await client.get("/api/v1/instructor/overview")
        assert overview.status_code == 200
        assert overview.json()["classGroups"] == []
        assert overview.json()["reviewQueue"] == []


@pytest.mark.asyncio
async def test_teacher_can_soft_delete_last_course_and_restore_all_source_data(client, native):
    from src.course_source.models import Assignment, Resource

    headers = await sign_in(client)
    with CourseSession() as db:
        db.add(Assignment(course_id=1, title="Preserved task", description="", due_at=datetime.now(UTC)))
        db.add(Resource(course_id=1, title="Preserved PDF", kind="file", source_url="/api/files/preserved.pdf"))
        db.commit()

    listed = await client.get("/api/v1/instructor/manage/courses")
    course = next(item for item in listed.json() if item["id"] == 1)
    removed = await client.post(
        "/api/v1/instructor/manage/courses/1/lifecycle/archive",
        headers=headers,
        json={"expected_version": course["version"]},
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["archived"] is True

    # The ordinary PaceWise source no longer exposes the course or its children.
    sync = await client.get("/api/v1/lms/sync", headers=headers)
    assert sync.status_code == 200, sync.text
    assert sync.json()["courses"] == []
    assert sync.json()["tasks"] == []

    restored = await client.post(
        "/api/v1/instructor/manage/courses/1/lifecycle/restore",
        headers=headers,
        json={"expected_version": removed.json()["version"]},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["archived"] is False
    after = await client.get("/api/v1/lms/sync", headers=headers)
    assert any(item["id"] == "1" for item in after.json()["courses"])
    assert any(item["title"] == "Preserved task" for item in after.json()["tasks"])


async def upload_pdf(client, headers, data, chapter="Chapter 3", filename="chapter.pdf"):
    ticket = await client.post("/api/v1/instructor/manage/courses/1/pdf-ticket", headers=headers,
                              json={"filename": filename, "chapter": chapter, "size": len(data)})
    assert ticket.status_code == 200
    path = ticket.json()["uploadPath"]
    uploaded = await client.put(path, content=data, headers={**headers, "Content-Type": "application/pdf"})
    assert uploaded.status_code == 204, uploaded.text
    receipt = await client.post("/api/v1/instructor/manage/courses/1/pdf-receipt", headers=headers,
                               json={"token": path.split("/")[-1]})
    assert receipt.status_code == 200
    return receipt.json()


def word_bytes(paragraphs):
    body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return output.getvalue()


@pytest.mark.asyncio
async def test_mixed_word_upload_keeps_teacher_original_and_indexes_public_derivative(client, native):
    from src.course_source.models import Resource, ResourceAccess
    from src.persistence_models import LmsFileIndex

    headers = await sign_in(client)
    data = word_bytes([
        "Bài tập theo buổi",
        "Buổi 1 – Class và object",
        "Tạo class Student và kiểm thử invariant.",
        "Rubric 100 điểm: nghiệp vụ 60; kiểm thử 40.",
        "Đáp án và rubric giữa kỳ",
        "Mã nguồn hoàn chỉnh chỉ dành cho giảng viên.",
    ])
    ticket = await client.post(
        "/api/v1/instructor/manage/courses/1/document-ticket",
        headers=headers,
        json={
            "filename": "oop-package.docx",
            "chapter": "Bài tập theo chương",
            "size": len(data),
            "content_role": "mixed_assignment_package",
        },
    )
    assert ticket.status_code == 200, ticket.text
    path = ticket.json()["uploadPath"]
    uploaded = await client.put(
        path,
        content=data,
        headers={
            **headers,
            "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
    )
    assert uploaded.status_code == 204, uploaded.text

    with CourseSession() as db:
        resources = db.scalars(select(Resource).order_by(Resource.id)).all()
        assert [item.kind for item in resources] == ["teacher_assignment_package", "assignment_guide"]
        private_access = db.scalars(
            select(ResourceAccess).where(ResourceAccess.resource_id == resources[0].id)
        ).all()
        assert [(item.scope_type, item.scope_id) for item in private_access] == [("instructor", 1)]
        public_url = resources[1].source_url
    public_text = (Path(native.course_upload_dir) / public_url.rsplit("/", 1)[-1]).read_text(encoding="utf-8")
    assert "Tạo class Student" in public_text
    assert "Mã nguồn hoàn chỉnh" not in public_text
    with SessionLocal() as db:
        jobs = db.scalars(select(LmsFileIndex)).all()
        assert len(jobs) == 1
        assert json.loads(jobs[0].metadata_json)["content_role"] == "student_assignment_brief"


@pytest.mark.asyncio
async def test_mixed_word_upload_fails_closed_without_an_answer_heading(client, native):
    headers = await sign_in(client)
    data = word_bytes(["Bài tập theo buổi", "Buổi 1 – Class", "Tạo class Student."])
    ticket = await client.post(
        "/api/v1/instructor/manage/courses/1/document-ticket",
        headers=headers,
        json={
            "filename": "ambiguous.docx",
            "chapter": "Bài tập theo chương",
            "size": len(data),
            "content_role": "mixed_assignment_package",
        },
    )
    path = ticket.json()["uploadPath"]
    uploaded = await client.put(
        path,
        content=data,
        headers={
            **headers,
            "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
    )

    assert uploaded.status_code == 422
    assert not list(Path(native.course_upload_dir).glob("*.docx"))


@pytest.mark.asyncio
async def test_same_pdf_same_chapter_deduplicates_without_cross_chapter_mapping(client, native):
    from pathlib import Path

    from src.course_source.models import ModuleItem, Resource

    headers = await sign_in(client)
    data = b"%PDF-1.4\nfixture"
    first = await upload_pdf(client, headers, data)
    repeated = await upload_pdf(client, headers, data, filename="renamed.pdf")
    assert repeated["fileId"] == first["fileId"] and repeated["duplicate"] and not first["duplicate"]
    assert len(list(Path(native.course_upload_dir).glob("*.pdf"))) == 1
    other = await upload_pdf(client, headers, data, "Chapter 4")
    assert other["fileId"] != first["fileId"] and not other["duplicate"]
    with CourseSession() as db:
        assert len(db.scalars(select(Resource)).all()) == 2
        assert len(db.scalars(select(ModuleItem).where(ModuleItem.item_type == "resource")).all()) == 2
    assert len(list(Path(native.course_upload_dir).glob("*.pdf"))) == 2


@pytest.mark.asyncio
async def test_native_pdf_queue_limits_and_explicit_retry(client, native, monkeypatch):
    from unittest.mock import AsyncMock

    from src.persistence_models import LmsFileIndex
    from src.services import lms_files
    from tests.test_services.test_lms_file_integration import pdf_bytes

    headers = await sign_in(client)
    uploaded = await upload_pdf(client, headers, pdf_bytes())
    identifier = f"{native.institution_id}:1:{uploaded['fileId']}"
    source = LMSClient(native)
    with SessionLocal() as db:
        assert db.get(LmsFileIndex, identifier).status == "queued"
    monkeypatch.setattr(lms_files, "bounded_extract", AsyncMock(side_effect=TimeoutError()))
    assert await lms_files.process_file_extractions(source, native) == 1
    with SessionLocal() as db:
        row = db.get(LmsFileIndex, identifier)
        assert row.status == "extraction_retry" and row.attempts == 1 and row.chunks_json == "[]"
    assert await lms_files.process_file_extractions(source, native) == 1
    assert await lms_files.process_file_extractions(source, native) == 1
    with SessionLocal() as db:
        row = db.get(LmsFileIndex, identifier)
        assert row.status == "failed" and row.attempts == native.worker_max_attempts and row.chunks_json == "[]"
        version = row.resource_version
    await lms_files.sync_course_files(source, native, 1, "N101")
    assert await lms_files.process_file_extractions(source, native) == 0  # No infinite sync reset.
    path = f"/api/v1/instructor/lms-files/1/{uploaded['fileId']}/retry"
    assert (await client.post(path, headers=headers, json={"expectedVersion": version})).status_code == 429
    with SessionLocal() as db:
        db.get(LmsFileIndex, identifier).updated_at = datetime.now(UTC) - timedelta(seconds=31)
        db.commit()
    assert (await client.post(path, headers=headers, json={"expectedVersion": "f" * 64})).status_code == 409
    assert (await client.post(path, headers=headers, json={"expectedVersion": version})).json()["status"] == "queued"
    assert (await client.post(path, headers=headers, json={"expectedVersion": version})).status_code == 409
    status = await client.get("/api/v1/instructor/lms-files/status?course_id=1")
    assert status.json()["files"][0]["version"] == version
    assert status.json()["files"][0]["view_url"] == f"/api/v1/lms-files/1/{uploaded['fileId']}/download"
    await client.post("/api/v1/auth/logout", headers=headers)
    student = await sign_in(client, "student@native.test")
    assert (await client.post(path, headers=student, json={"expectedVersion": version})).status_code == 403


@pytest.mark.asyncio
async def test_upload_queue_admission_includes_reserved_tickets(client, native):
    limited = native.model_copy(update={"course_file_queue_limit": 1})
    app.dependency_overrides[get_settings] = lambda: limited
    headers = await sign_in(client)
    payload = {"filename": "one.pdf", "chapter": "Chapter 3", "size": 5}
    assert (await client.post("/api/v1/instructor/manage/courses/1/pdf-ticket", headers=headers, json=payload)).status_code == 200
    second = await client.post("/api/v1/instructor/manage/courses/1/pdf-ticket", headers=headers, json=payload)
    assert second.status_code == 429 and second.headers["Retry-After"] == "30"


@pytest.mark.asyncio
async def test_disconnect_during_register_commit_preserves_committed_file(native, monkeypatch):
    import asyncio
    import threading
    from pathlib import Path
    from types import SimpleNamespace

    from src.api import course_uploads
    from src.course_source.models import Resource

    data = b"%PDF-1.4\nfixture"
    spec = {"course_id": 1, "filename": "cancel.pdf", "chapter": "Chapter 3", "size": len(data)}
    monkeypatch.setattr(course_uploads, "claim_ticket", lambda *_: spec)
    entered, release = threading.Event(), threading.Event()
    original = course_uploads.register_pdf

    def slow_register(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(course_uploads, "register_pdf", slow_register)

    class Request:
        headers = {"content-type": "application/pdf", "content-length": str(len(data))}

        async def stream(self):
            yield data

    task = asyncio.create_task(course_uploads.receive_binary("a" * 43, Request(), SimpleNamespace(role="instructor", user_id=1), native))
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    with CourseSession() as db:
        resource = db.scalar(select(Resource))
        assert resource
        path = Path(native.course_upload_dir) / resource.source_url.split("/")[-1]
        assert path.read_bytes() == data


@pytest.mark.asyncio
async def test_login_preserves_identity_and_logout_really_revokes_without_lms(client, native):
    headers = await sign_in(client)
    token = client.cookies["pacewise_session"]
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 200 and response.json()["user"]["id"] == "1"
    assert "password" not in response.text and "access_token" not in response.text
    response = await client.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == 200 and response.json()["ok"]
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers={"Cookie": "pacewise_session=" + token})).status_code == 401


@pytest.mark.asyncio
async def test_native_role_ownership_and_course_management(client, native):
    headers = await sign_in(client)
    listed = await client.get("/api/v1/instructor/manage/courses")
    assert listed.status_code == 200 and [item["id"] for item in listed.json()] == [1]
    assert (await client.get("/api/v1/instructor/manage/courses/2")).status_code == 403
    response = await client.post("/api/v1/instructor/manage/courses", headers=headers,
                                 json={"code": "CREATED", "name": "Created locally", "student_ids": [2]})
    assert response.status_code == 201, response.text
    created = response.json()["id"]
    assert created > 2
    with CourseSession() as db:
        assert db.get(Course, created).name == "Created locally"
    await client.post("/api/v1/auth/logout", headers=headers)
    student_headers = await sign_in(client, "student@native.test")
    assert (await client.get("/api/v1/instructor/manage/courses")).status_code == 403
    assert (await client.post("/api/v1/instructor/manage/courses", headers=student_headers,
                              json={"code": "NO", "name": "No"})).status_code == 403
    assert (await client.get("/api/pacewise/v1/courses")).status_code == 404


@pytest.mark.asyncio
async def test_native_task_material_module_mapping_and_summary(client, native):
    headers = await sign_in(client)
    material = await client.post("/api/v1/instructor/manage/courses/1/materials", headers=headers,
        json={"title": "Correct chapter", "chapter": "Chapter 3", "content": "Allowed facts about partial orders."})
    assert material.status_code == 201, material.text
    task = await client.post("/api/v1/instructor/manage/courses/1/tasks", headers=headers, json={
        "title": "Task chapter 3", "kind": "assignment", "description": "Explain partial orders",
        "due_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(), "points_possible": 10,
        "published": True, "chapter": "Chapter 3",
    })
    assert task.status_code == 201, task.text
    client_source = LMSClient(native)
    assignments, modules, content = await client_source.service_get_many([
        ("/api/pacewise/v1/courses/1/assignments", {"user_id": 2}),
        ("/api/pacewise/v1/courses/1/modules", {"user_id": 2}),
        ("/api/pacewise/v1/courses/1/content", {"user_id": 2}),
    ])
    assert assignments and modules and content
    assert assignments[0]["title"] == "Task chapter 3"
    assert modules[0]["name"] == "Chapter 3"
    assert (await client_source.service_get("/api/pacewise/v1/events", {"after_id": 0}))


@pytest.mark.asyncio
async def test_instructor_summary_contract_is_minimal_and_keeps_first_attempt_state(client, native):
    from src.course_source.models import Assignment, Submission, SubmissionAttempt, SubmissionDetail, SubmissionWorkflow

    now = datetime.now(UTC)
    with CourseSession() as db:
        db.add(Assignment(id=50, course_id=1, title="Summary task", description="private detail",
                          due_at=now + timedelta(days=1), points_possible=10, published=True))
        db.flush()
        db.add(Submission(id=50, assignment_id=50, user_id=2, submitted_at=now,
                          workflow_state="graded", score=9, late=False))
        db.add(SubmissionDetail(submission_id=50, instructor_comment="private feedback", rubric_json='{"x": 1}'))
        db.add(SubmissionWorkflow(submission_id=50, excused=True, reassigned=False))
        db.add(SubmissionAttempt(submission_id=50, attempt_number=1, submitted_at=now - timedelta(minutes=5)))
        db.commit()
    source = LMSClient(native)
    assignments = await source.service_get("/api/pacewise/v1/courses/1/assignments", {"summary": True})
    submissions = await source.service_get("/api/pacewise/v1/courses/1/submissions", {"summary": True})
    assert assignments == [{"id": 50, "course_id": 1, "title": "Summary task",
                            "due_at": (now + timedelta(days=1)).isoformat(), "published": True,
                            "student_due_dates": {}}]
    assert submissions[0]["workflow_state"] == "excused"
    assert submissions[0]["attempt_count"] == 1
    assert submissions[0]["first_submitted_at"] == (now - timedelta(minutes=5)).isoformat()
    assert "feedback" not in submissions[0] and "rubric" not in submissions[0]


@pytest.mark.asyncio
async def test_pdf_binary_ticket_one_time_and_live_acl(client, native):
    from src.course_source.models import Resource

    headers = await sign_in(client)
    data = b"%PDF-1.4\n" + b"x" * (6 * 1024 * 1024)
    response = await client.post("/api/v1/instructor/manage/courses/1/pdf-ticket", headers=headers,
                                json={"filename": "large.pdf", "chapter": "Chapter 3", "size": len(data)})
    assert response.status_code == 200, response.text
    path = response.json()["uploadPath"]
    assert "courses/1" not in path
    binary_headers = {**headers, "Content-Type": "application/pdf"}
    response = await client.put(path, content=data, headers=binary_headers)
    assert response.status_code == 204 and not response.content
    assert (await client.put(path, content=data, headers=binary_headers)).status_code == 409
    with CourseSession() as db:
        resource = db.scalar(select(Resource).where(Resource.course_id == 1))
        identifier = resource.id
    assert await LMSClient(native).download_course_file(1, identifier, user_id=2) == data
    with pytest.raises(Exception) as forbidden:
        await LMSClient(native).download_course_file(1, identifier, user_id=3)
    assert forbidden.value.status_code == 403
    assert (await client.post("/api/v1/instructor/manage/courses/1/pdf-ticket", headers=headers,
                              json={"filename": "../bad.pdf", "chapter": "Chapter 3", "size": 10})).status_code == 422


@pytest.mark.asyncio
async def test_pdf_failed_signature_leaves_no_file_and_expired_session_cannot_upload(client, native):
    headers = await sign_in(client)
    ticket = await client.post("/api/v1/instructor/manage/courses/1/pdf-ticket", headers=headers,
                               json={"filename": "bad.pdf", "chapter": "Chapter 3", "size": 5})
    path = ticket.json()["uploadPath"]
    assert (await client.put(path, content=b"wrong", headers={**headers, "Content-Type": "application/pdf"})).status_code == 422
    from pathlib import Path

    assert not list(Path(native.course_upload_dir).glob("*.pdf"))
    await client.post("/api/v1/auth/logout", headers=headers)
    assert (await client.put(path, content=b"wrong", headers={**headers, "Content-Type": "application/pdf"})).status_code == 401


def test_snapshot_lossless_all_tables_hashes_idempotent_and_never_overwrites(native, tmp_path):
    path = tmp_path / "snapshot.jsonl.gz"
    expected = export_snapshot(path, str(engine.url))
    assert expected["tables"] == len(Base.metadata.tables)
    result = import_snapshot(path)
    assert result["already_imported"] and result["inventory"] == expected["inventory"]
    with CourseSession() as db:
        db.get(User, 2).full_name = "Newer record"
        db.commit()
    with pytest.raises(ValueError, match="refusing to overwrite"):
        import_snapshot(path)
    with CourseSession() as db:
        assert db.get(User, 2).full_name == "Newer record"


def test_snapshot_empty_target_preserves_accounts_ids_and_credentials(native, tmp_path):
    path = tmp_path / "snapshot.jsonl.gz"
    expected = export_snapshot(path, str(engine.url))
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(delete(table))
    result = import_snapshot(path)
    assert not result["already_imported"] and result["inventory"] == expected["inventory"]
    with CourseSession() as db:
        assert db.get(User, 2).password_hash == password_hash("native-test")


@pytest.mark.asyncio
async def test_native_login_rejects_wrong_password_and_lms_bridges(client, native):
    wrong = await client.post("/api/v1/auth/login", json={"email": "teacher@native.test", "password": "wrong"})
    assert wrong.status_code == 401
    unknown = await client.post("/api/v1/auth/login", json={"email": "unknown@native.test", "password": "wrong"})
    assert unknown.status_code == 401 and unknown.json() == wrong.json()
    headers = await sign_in(client)
    assert (await client.post("/api/v1/auth/lms-bridge", headers=headers)).status_code == 410
    assert (await client.post("/api/v1/auth/lms-launch", json={"token": "x" * 30})).status_code == 410


@pytest.mark.asyncio
async def test_confirmed_do_uses_native_chapter_only_and_starts_timer(client, native):
    from src.course_source.models import Assignment
    from src.course_source.teacher_management import MaterialInput, map_chapter, save_material
    from src.persistence_models import LearnerMemory, StudyTimerSession

    with CourseSession() as db:
        task = Assignment(course_id=1, title="Native chapter task", description="Explain the relation",
                          due_at=datetime.now(UTC) + timedelta(days=4), points_possible=10, submission_types="online_text_entry")
        db.add(task)
        db.flush()
        task_id = task.id
        map_chapter(db, 1, "Chapter 3", "assignment", task.id, task.title)
        save_material(db, 1, 1, MaterialInput(title="Correct chapter", chapter="Chapter 3", content="Partial order lesson"), commit=False)
        save_material(db, 1, 1, MaterialInput(title="Other chapter", chapter="Chapter 4", content="Do not retrieve this"), commit=False)
        db.commit()
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
    block_id = "native-confirmed-do"
    with SessionLocal() as db:
        identifier = f"{native.institution_id}:2:1"
        row = db.get(LearnerMemory, identifier) or LearnerMemory(id=identifier, institution_id=native.institution_id,
                                                                user_id=2, course_id=1)
        profile = json.loads(row.profile_json or "{}")
        profile["last_confirmed_plan"] = {"blocks": [{"id": block_id, "taskId": f"1:{task_id}", "date": tomorrow,
            "start": "09:00", "end": "09:30", "status": "confirmed", "milestoneTitle": "Explain partial orders"}]}
        row.profile_json = json.dumps(profile)
        db.add(row)
        db.execute(delete(StudyTimerSession).where(StudyTimerSession.user_id == 2))
        db.commit()
    headers = await sign_in(client, "student@native.test")
    response = await client.post("/api/v1/study-sessions/prepare", headers=headers, json={"courseId": 1, "blockId": block_id})
    assert response.status_code == 200, response.text
    assert "Correct chapter" in response.text and "Other chapter" not in response.text
    assert response.json()["scope"]["status"] == "mapped"
    started = await client.post("/api/v1/study-sessions", headers=headers, json={"courseId": 1, "blockId": block_id})
    assert started.status_code == 200 and started.json()["status"] == "running"
    ended = await client.post(f"/api/v1/study-sessions/{started.json()['id']}/events", headers=headers, json={
        "action": "complete", "eventKey": "native-complete-once", "expectedVersion": started.json()["version"],
        "completionPercent": 30, "lengthFeeling": "comfortable", "blocker": "none"})
    assert ended.status_code == 200, ended.text


@pytest.mark.asyncio
async def test_login_sync_and_plan_context_release_main_transaction_before_native_dispatch(client, native, monkeypatch):
    from src.api.routes import _load_lms_agent_context
    from src.security import decode_session

    tracked = SessionLocal()
    app.dependency_overrides[pacewise_get_db] = lambda: tracked
    original_login = LMSClient.login_and_create_launch
    original_get = LMSClient.service_get

    async def checked_login(self, *args, **kwargs):
        assert not tracked.in_transaction(), "Login kept main pool while awaiting native authentication"
        return await original_login(self, *args, **kwargs)

    async def checked_get(self, *args, **kwargs):
        assert not tracked.in_transaction(), "Source query started with a main DB transaction still checked out"
        return await original_get(self, *args, **kwargs)

    monkeypatch.setattr(LMSClient, "login_and_create_launch", checked_login)
    monkeypatch.setattr(LMSClient, "service_get", checked_get)
    try:
        await sign_in(client)
        response = await client.get("/api/v1/lms/sync")
        assert response.status_code == 200, response.text
        context = decode_session(client.cookies["pacewise_session"], native, tracked)
        result = await _load_lms_agent_context(context, native, tracked, force_refresh=True)
        assert result["course_id"] == "1"
    finally:
        app.dependency_overrides.pop(pacewise_get_db, None)
        tracked.close()
