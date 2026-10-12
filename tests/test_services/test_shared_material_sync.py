from src.api.lms_integration import _shared_resource_manifest


def test_student_sync_contains_only_shared_resource_manifest():
    source = [{
        "id": 47,
        "title": "Chương 1.pdf",
        "kind": "slides",
        "source_url": "/api/files/course-35-sha.pdf",
        "folder": None,
        "latest_version": {
            "id": 99,
            "version": 1,
            "checksum_sha256": "abc",
            "size_bytes": 1234,
            "content_type": "application/pdf",
            "created_at": "2026-10-11T00:00:00Z",
        },
        "access_scope": [{"type": "course", "id": 35, "permission": "view"}],
        "content": "must not cross the sync boundary",
        "chunks": [{"text": "must not be copied per student"}],
        "embedding": [0.1, 0.2],
    }]

    first = _shared_resource_manifest(source)
    second = _shared_resource_manifest(source)

    assert first == second
    assert first[0]["id"] == 47
    assert first[0]["access_scope"] == [{"type": "course", "id": 35}]
    assert set(first[0]) == {
        "id", "title", "kind", "source_url", "folder", "latest_version", "access_scope"
    }
    assert set(first[0]["latest_version"]) == {
        "version", "checksum_sha256", "content_type", "created_at"
    }
