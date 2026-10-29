"""Integration evidence: real simulator HTTP, real PDF parsing, real in-memory Qdrant.

Embeddings are deterministic test vectors, not an evaluation of semantic model quality.
"""

import hashlib
import io
import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.agents.tools import qdrant_retriever as rag
from src.config import get_settings
from src.db import Base, SessionLocal
from src.persistence_models import LmsFileIndex
from src.services import lms_files
from src.services.lms_client import LMSClient

TEST_SERVICE_KEY = "pacewise-integration-test-key"


@pytest.fixture(autouse=True)
def isolated_file_database(monkeypatch):
    import sys

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(lms_files, "SessionLocal", factory)
    monkeypatch.setattr(sys.modules[__name__], "SessionLocal", factory)
    yield factory
    engine.dispose()


def pdf_bytes(text="A relation is a subset of A cross B."):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(600, 800)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture
def vector_backend(monkeypatch):
    # In-memory Qdrant/embedding spies cannot cross a process boundary. Other
    # tests exercise the real process timeout; here the same index operation
    # runs inline against deterministic vectors.
    from src.services.file_indexing import index_file_job

    monkeypatch.setattr(lms_files, "bounded_index", index_file_job)
    qdrant = QdrantClient(":memory:")
    calls = []

    class Embed:
        def embed(self, texts):
            values = list(texts)
            calls.extend(values)
            return [[1.0] + [0.0] * 383 for _ in values]

    monkeypatch.setattr(rag, "_get_qdrant_client", lambda *_args: qdrant)
    monkeypatch.setattr(rag, "_get_embedding_model", lambda: Embed())
    monkeypatch.setattr(rag, "rerank_passages", lambda _q, passages, top_k: passages[:top_k])
    yield qdrant, calls
    qdrant.close()


@pytest.fixture
def simulator(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "lms-simulator"))
    monkeypatch.setenv("PACEWISE_API_KEY", TEST_SERVICE_KEY)
    get_settings.cache_clear()
    from app import extended_api, security
    from app.db import Base, get_db
    from app.main import app
    from app.models import Course, Enrollment, User

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        for identifier, role in [(1, "instructor"), (2, "student"), (3, "student")]:
            db.add(
                User(
                    id=identifier,
                    email=f"{role}{identifier}@test.edu",
                    full_name=role,
                    password_hash=security.hash_password("demo12345"),
                    role=role,
                    avatar_color="#000000",
                )
            )
            db.add(Enrollment(user_id=identifier, course_id=77, role=role))
        db.add(Course(id=77, code="TRR", name="Relations", term="Demo", color="#000000"))
        db.commit()

    def database():
        with factory() as db:
            yield db

    original = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = database
    monkeypatch.setattr(security, "SessionLocal", factory)
    monkeypatch.setattr(extended_api, "UPLOAD_DIR", tmp_path)
    try:
        yield app
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)
        engine.dispose()
        get_settings.cache_clear()


async def login(client, email):
    result = await client.post("/api/session", json={"email": email, "password": "demo12345"})
    assert result.status_code == 200
    return {"Authorization": "Bearer " + client.cookies["canvas_session"]}


@pytest.mark.asyncio
async def test_real_simulator_quiz_override_flows_into_pacewise_plan_and_completion(simulator, monkeypatch):
    from datetime import UTC, datetime

    from src.api import lms_integration, routes
    from src.security import SessionContext
    from src.services.planning import build_plan_draft
    settings = get_settings()
    session = SessionContext(2, 77, (77,), "student", "Learner", "student2@test.edu", "test", "test", 4102444800)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator), base_url="http://lms.test") as http:
        teacher = await login(http, "instructor1@test.edu")
        student = await login(http, "student2@test.edu")
        client = LMSClient(settings, http)
        created = await http.post("/api/courses/77/content/quiz", headers=teacher,
                                  json={"user_id": 1, "title": "Relations", "body": "Chapter 3", "due_at": "2099-10-08T05:17:00Z", "points_possible": 2, "published": True})
        assert created.status_code == 200, created.text
        quiz_id = created.json()["id"]
        question = await http.post(f"/api/quizzes/{quiz_id}/questions", headers=teacher,
                                   json={"user_id": 1, "prompt": "Is equality symmetric?", "options": ["yes", "no"], "correct_answer": "yes", "points": 2})
        assert question.status_code == 200, question.text
        assignment_id = (await client.service_get("/api/pacewise/v1/courses/77/assignments", {"user_id": 2}))[0]["id"]
        override = await http.post(f"/api/assignments/{assignment_id}/overrides", headers=teacher,
                                   json={"title": "Extra hour", "target_type": "student", "target_id": 2, "due_at": "2099-10-08T06:17:00Z"})
        assert override.status_code == 201, override.text
        # Editable planner dates must not replace the effective LMS deadline.
        await http.post("/api/planner", headers=student,
                        json={"course_id": 77, "assignment_id": assignment_id, "title": "Fake", "due_at": "2099-12-31T00:00:00Z", "completed": True})
        monkeypatch.setattr(routes, "LMSClient", lambda _settings: client)
        context = await routes._load_lms_agent_context(session, settings)
        assignment = context["assignments"][0]
        assert assignment["deadline"].startswith("2099-10-08T06:17") and assignment["submission"] is None
        assert assignment["deadline"].endswith('+00:00')  # SQLite must not strip the API's UTC semantics.
        other_session = SessionContext(3, 77, (77,), "student", "Other", "student3@test.edu", "test", "other", 4102444800)
        other_context = await routes._load_lms_agent_context(other_session, settings)
        assert other_context["assignments"][0]["deadline"].startswith("2099-10-08T05:17")
        inputs = {"weekStart": "2099-10-05", "tasks": [{"taskId": assignment["id"], "remainingMin": 60}],
                  "availability": [{"weekday": 3, "enabled": True, "start": "17:00", "end": "21:00"}]}
        draft = build_plan_draft(inputs, context["assignments"], now=datetime(2099, 10, 8, 3, tzinfo=UTC))
        assert draft["blocks"] == [] and not draft["qualityEvaluation"]["canConfirm"]
        assert draft['expiredTasks'] == []  # 13:17 local is still ahead of 10:00 local.
        submitted = await http.post(f"/api/quizzes/{quiz_id}/attempts", headers=student,
                                    json={"user_id": 2, "answers": {str(question.json()["id"]): "yes"}})
        assert submitted.status_code == 200, submitted.text
        context = await routes._load_lms_agent_context(session, settings)
        assert context["assignments"][0]["submission"]["workflow_state"] == "graded"
        tasks, _ = await lms_integration._course_snapshot(client, {"id": 77}, session, [])
        assert tasks[0]["status"] == "done" and tasks[0]["submission"]["score"] == 2


def hits(versions):
    return rag.search_course_materials(
        "relation", institution_id=get_settings().institution_id, course_id="77", authorized_file_versions=versions
    )["passages"]


@pytest.mark.asyncio
async def test_explicit_course_subject_mismatch_is_not_indexed(monkeypatch):
    settings = get_settings()
    data = b"valid-placeholder"
    item = {
        "id": 501,
        "title": "Co_So_Du_Lieu.docx",
        "kind": "assignment_guide",
        "content_role": "student_assignment_brief",
        "course_name": "Nhập môn lập trình Python",
        "source_url": "/api/files/course-77-database.docx",
        "latest_version": {
            "version": 1,
            "checksum_sha256": hashlib.sha256(data).hexdigest(),
        },
    }
    client = AsyncMock()
    client.service_get.return_value = [item]
    client.download_course_file.return_value = data
    monkeypatch.setattr(
        lms_files,
        "bounded_extract",
        AsyncMock(return_value=[{
            "section_title": "BÀI TẬP MÔN CƠ SỞ DỮ LIỆU",
            "content": "BÀI TẬP MÔN CƠ SỞ DỮ LIỆU",
        }]),
    )

    await lms_files.sync_course_files(client, settings, 77, "CS101")
    assert await lms_files.process_file_extractions(client, settings) == 1

    with SessionLocal() as db:
        row = db.get(LmsFileIndex, f"{settings.institution_id}:77:501")
        assert row.status == "failed"
        assert row.failure_reason == "CourseSubjectMismatchError"
        assert "tên môn khác" in row.last_error
        assert json.loads(row.chunks_json) == []


@pytest.mark.asyncio
async def test_pdf_upload_index_update_revoke_restore_delete(simulator, vector_backend):
    settings = get_settings()
    qdrant, embeds = vector_backend
    with SessionLocal() as db:
        db.query(LmsFileIndex).filter(LmsFileIndex.course_id == 77).delete()
        db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator), base_url="http://lms.test") as http:
        teacher = await login(http, "instructor1@test.edu")
        student = await login(http, "student2@test.edu")
        client = LMSClient(settings, http)
        upload = await http.post(
            "/api/courses/77/resources/upload",
            headers=teacher,
            data={"user_id": 1},
            files={"upload": ("relations.pdf", pdf_bytes(), "application/pdf")},
        )
        assert upload.status_code == 200, upload.text
        spoofed = await http.post(
            "/api/courses/77/resources/upload",
            headers=student,
            data={"user_id": 1},
            files={"upload": ("spoof.pdf", pdf_bytes(), "application/pdf")},
        )
        assert spoofed.status_code == 403
        item = upload.json()
        identifier = item["id"]
        await lms_files.sync_course_files(client, settings, 77, "TRR")
        await lms_files.process_file_extractions(client, settings)
        assert lms_files.process_file_indexes(settings) == 1
        manifest = await lms_files.authorized_files(client, 77, 2)
        versions = {f"file:{item['id']}": lms_files.file_version(item) for item in manifest}
        passages = hits(versions)
        assert passages and passages[0]["page"] == 1
        assert "subset of A cross B" in passages[0]["content"]
        assert passages[0]["download_url"] == f"/api/v1/lms-files/77/{identifier}/download"
        before = len(embeds)
        await lms_files.sync_course_files(client, settings, 77, "TRR")
        await lms_files.process_file_extractions(client, settings)
        assert lms_files.process_file_indexes(settings) == 0
        assert len(embeds) == before
        # Change permission BEFORE any worker cleanup. Query must already exclude it.
        result = await http.put(f"/api/resources/{identifier}/access", headers=teacher, json={"published": False})
        assert result.status_code == 200, result.text
        assert await lms_files.authorized_files(client, 77, 2) == []
        assert hits({}) == []
        with pytest.raises(Exception) as denied:
            await client.download_course_file(77, identifier, user_id=2)
        assert denied.value.status_code == 403
        assert (await http.get(f"/api/resources/{identifier}/versions", headers=student)).status_code == 403
        await lms_files.sync_course_files(client, settings, 77, "TRR")
        await lms_files.process_file_extractions(client, settings)
        lms_files.process_file_indexes(settings)
        assert qdrant.count("course_materials").count == 0
        # Restore only for one learner, then replace content without resetting the ACL.
        result = await http.put(
            f"/api/resources/{identifier}/access", headers=teacher, json={"published": True, "target_user_id": 2}
        )
        assert result.status_code == 200, result.text
        assert await lms_files.authorized_files(client, 77, 3) == []
        replaced = await http.put(
            f"/api/courses/77/resources/{identifier}/upload",
            headers=teacher,
            data={"user_id": 1},
            files={"upload": ("new.pdf", pdf_bytes("A symmetric relation reverses every pair."), "application/pdf")},
        )
        assert replaced.status_code == 200
        assert replaced.json()["latest_version"]["version"] == 2
        assert await lms_files.authorized_files(client, 77, 3) == []
        before_index = (await lms_files.authorized_files(client, 77, 2))[0]
        assert hits({f"file:{identifier}": lms_files.file_version(before_index)}) == []
        await lms_files.sync_course_files(client, settings, 77, "TRR")
        await lms_files.process_file_extractions(client, settings)
        lms_files.process_file_indexes(settings)
        latest = (await lms_files.authorized_files(client, 77, 2))[0]
        new_versions = {f"file:{identifier}": lms_files.file_version(latest)}
        assert hits(versions) == []
        assert "symmetric" in hits(new_versions)[0]["content"]
        deleted = await http.delete(f"/api/courses/77/resources/{identifier}?user_id=1", headers=teacher)
        assert deleted.status_code == 200
        assert await lms_files.authorized_files(client, 77, 2) == []
        assert hits({}) == []
        await lms_files.sync_course_files(client, settings, 77, "TRR")
        await lms_files.process_file_extractions(client, settings)
        lms_files.process_file_indexes(settings)
        assert qdrant.count("course_materials").count == 0
        events = await client.service_get("/api/pacewise/v1/events")
        assert {"resource.created", "resource.updated", "resource.access.updated", "resource.deleted"} <= {
            event["type"] for event in events
        }


@pytest.mark.asyncio
async def test_authenticated_pdf_proxy_and_non_enrolled_access(simulator, monkeypatch):
    from src.api import lms_files as file_api
    from src.main import app as pacewise
    from src.security import SessionContext, get_current_session

    settings = get_settings()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator), base_url="http://lms.test") as http:
        teacher = await login(http, "instructor1@test.edu")
        result = await http.post(
            "/api/courses/77/resources/upload",
            headers=teacher,
            data={"user_id": 1},
            files={"upload": ("relations.pdf", pdf_bytes(), "application/pdf")},
        )
        file_id = result.json()["id"]
        monkeypatch.setattr(file_api, "LMSClient", lambda _settings: LMSClient(settings, http))
        session = SessionContext(2, 77, (77,), "student", "Student", "student2@test.edu", "csrf", "session", 4102444800)
        original = dict(pacewise.dependency_overrides)
        pacewise.dependency_overrides[get_current_session] = lambda: session
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=pacewise), base_url="http://pacewise.test"
            ) as backend:
                url = f"/api/v1/lms-files/77/{file_id}/download"
                response = await backend.get(url)
                assert response.status_code == 200
                assert response.content.startswith(b"%PDF")
                assert response.headers["content-type"] == "application/pdf"
                assert set(response.headers["cache-control"].split(", ")) == {"private", "no-store"}
                assert (await backend.get(f"/api/v1/lms-files/78/{file_id}/download")).status_code == 403
                await http.put(f"/api/resources/{file_id}/access", headers=teacher, json={"published": False})
                assert (await backend.get(url)).status_code == 403
        finally:
            pacewise.dependency_overrides.clear()
            pacewise.dependency_overrides.update(original)


@pytest.mark.asyncio
async def test_external_source_is_not_fetched_and_service_key_is_required(simulator):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator), base_url="http://lms.test") as http:
        teacher = await login(http, "instructor1@test.edu")
        item = await http.post(
            "/api/courses/77/resources",
            headers=teacher,
            json={
                "user_id": 1,
                "title": "Untrusted URL",
                "kind": "link",
                "source_url": "http://169.254.169.254/latest/meta-data/",
            },
        )
        identifier = item.json()["id"]
        endpoint = f"/api/pacewise/v1/courses/77/files/{identifier}/download"
        assert (await http.get(endpoint)).status_code in {401, 403}
        assert (
            await http.get(endpoint, headers={"X-PaceWise-Key": get_settings().pacewise_api_key})
        ).status_code == 422


@pytest.mark.asyncio
async def test_checksum_failure_and_failed_manifest_do_not_reuse_old_text(monkeypatch):
    settings = get_settings()
    client = AsyncMock()
    item = {
        "id": 99,
        "title": "bad.pdf",
        "source_url": "/api/files/bad.pdf",
        "latest_version": {"version": 1, "checksum_sha256": "0" * 64},
    }
    client.service_get.return_value = [item]
    client.download_course_file.return_value = pdf_bytes()
    await lms_files.sync_course_files(client, settings, 79, "TRR")
    await lms_files.process_file_extractions(client, settings)
    with SessionLocal() as db:
        row = db.get(LmsFileIndex, f"{settings.institution_id}:79:99")
        assert row.status == "failed" and json.loads(row.chunks_json) == []
    client.service_get.side_effect = RuntimeError("LMS unavailable")
    with pytest.raises(RuntimeError):
        await lms_files.sync_course_files(client, settings, 79, "TRR")
        await lms_files.process_file_extractions(client, settings)
    with SessionLocal() as db:
        assert db.get(LmsFileIndex, f"{settings.institution_id}:79:99").status == "failed"


@pytest.mark.parametrize(
    "name,data", [("bad.pdf", b"not a pdf"), ("bad.docx", b"not a zip"), ("bad.pptx", b"not a zip")]
)
def test_corrupt_documents_are_rejected(name, data):
    with pytest.raises((ValueError, __import__("zipfile").BadZipFile)):
        lms_files.validate_document(data, name)


def test_idempotent_vector_ingestion_survives_restart_and_delete(vector_backend):
    qdrant, embeds = vector_backend
    chunk = {
        "institution_id": "test",
        "course_id": "77",
        "resource_id": "file:1",
        "source_type": "lms_file",
        "resource_version": "v1",
        "access_scope": "course",
        "content": "Relations",
        "page": 1,
    }
    assert rag.ingest_course_resources([chunk])["status"] == "success"
    before = len(embeds)
    rag._ingested_resource_sets.clear()
    assert rag.ingest_course_resources([chunk])["status"] == "unchanged"
    assert len(embeds) == before
    # Deletion followed by restored same content must recreate vectors, not trust process cache.
    rag.delete_lms_file_resources(institution_id="test", course_id="77", resource_id="file:1")
    assert rag.ingest_course_resources([chunk])["status"] == "success"
    assert qdrant.count("course_materials").count == 1


def test_text_snapshot_cleanup_does_not_delete_lms_file_vectors(vector_backend):
    qdrant, _ = vector_backend
    rag.ingest_course_resources(
        [
            {
                "institution_id": "test",
                "course_id": "77",
                "resource_id": "file:1",
                "source_type": "lms_file",
                "resource_version": "v1",
                "access_scope": "course",
                "content": "Relations",
            }
        ]
    )
    rag.delete_course_resources(institution_id="test", course_id="77")
    rag.delete_stale_course_resources(institution_id="test", course_id="77", current_snapshot_version="text-v2")
    assert qdrant.count("course_materials").count == 1
