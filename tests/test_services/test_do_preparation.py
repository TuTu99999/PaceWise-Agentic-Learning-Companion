from src.services.do_preparation import resolve_scope


def module(identifier, assignment, file_ids):
    return {"id": identifier, "name": f"Chapter {identifier}", "published": True,
        "items": [{"id": 100, "type": "assignment", "content_id": assignment, "published": True},
                  *[{"id": file_id, "type": "file", "content_id": file_id, "published": True} for file_id in file_ids]]}


def file(identifier, kind="slides", url=None):
    return {"id": identifier, "title": f"Resource {identifier}", "kind": kind,
        "source_url": url or f"/api/files/course-1-{identifier}.pdf",
        "latest_version": {"version": 1, "checksum_sha256": f"hash{identifier}"}}


def test_filters_chapter_before_ranking_and_supplements_with_one_video():
    files = [file(1), file(2), file(3, "video"), file(4, "video"), file(5, "practice")]
    result = resolve_scope({"id": 7}, [module(1, 8, [1]), module(3, 7, [2, 3, 4, 5])], files, 1)
    assert result["scope"]["module_ids"] == ["3"]
    assert [resource["id"] for resource in result["resources"]] == ["file:2", "file:5", "file:3"]
    assert "file:1" not in result["versions"]


def test_missing_mapping_is_not_title_matching():
    result = resolve_scope({"id": 7, "title": "Chapter 3 Resource 1"}, [module(3, 8, [1])], [file(1)], 1)
    assert result["scope"]["status"] == "unmapped"
    assert result["resources"] == [] and result["versions"] == {}


def test_revoked_files_and_unpublished_modules_or_items_are_excluded():
    hidden = module(2, 7, [2])
    hidden["published"] = False
    visible = module(3, 7, [1, 2])
    visible["items"][-1]["published"] = False
    result = resolve_scope({"id": 7}, [hidden, visible], [file(2)], 1)
    assert result["resources"] == []


def test_dedup_by_hash_url_and_id_and_version_change():
    a, b, c = file(1), file(2), file(3)
    b["latest_version"]["checksum_sha256"] = a["latest_version"]["checksum_sha256"]
    c["source_url"] = a["source_url"]
    first = resolve_scope({"id": 7}, [module(3, 7, [1, 2, 3, 1])], [a, b, c], 1)
    assert len(first["resources"]) == 1
    a["latest_version"]["version"] = 2
    second = resolve_scope({"id": 7}, [module(3, 7, [1, 2, 3])], [a, b, c], 1)
    assert first["resource_version"] != second["resource_version"]


def test_legacy_external_file_requires_authorized_manifest_match():
    m = module(3, 7, [])
    m["items"].append({"id": 5, "type": "file", "external_url": "/static/mock-files/slide.pdf"})
    result = resolve_scope({"id": 7}, [m], [file(1, url="/static/mock-files/slide.pdf")], 1)
    assert result["resources"][0]["url"] == "/api/v1/lms-files/1/1/download"
    assert resolve_scope({"id": 7}, [m], [], 1)["resources"] == []


def test_empty_scope_does_not_even_contact_vector_store():
    from src.agents.tools.qdrant_retriever import search_course_materials
    class ForbiddenClient:
        def collection_exists(self, name):
            raise AssertionError("Unmapped Do scope must not retrieve other chapters")
    result = search_course_materials("Chapter 3", allowed_resource_ids=[], client=ForbiddenClient())
    assert result["insufficient_sources"] and result["passages"] == []


def test_text_pages_require_authorized_content_and_exact_chapter_mapping():
    one = module(1, 7, [])
    one["items"].append({"id": 23, "type": "page", "content_id": 2, "title": "Guide", "published": True})
    other = module(2, 9, [])
    other["items"].append({"id": 24, "type": "page", "content_id": 3, "title": "Other guide", "published": True})
    contents = [{"id": 2, "kind": "page", "title": "Guide", "body": "Grounded guidance", "published": True},
                {"id": 3, "kind": "page", "title": "Other guide", "body": "Wrong chapter", "published": True}]
    result = resolve_scope({"id": 7}, [one, other], [], 1, contents)
    assert [item["id"] for item in result["resources"]] == ["page:1:2"]
    assert result["resources"][0]["content"] == "Grounded guidance"
    assert resolve_scope({"id": 7}, [one], [], 1, [contents[1]])["resources"] == []
    changed = [{**contents[0], "body": "Updated guide"}]
    assert resolve_scope({"id": 7}, [one], [], 1, changed)["resource_version"] != result["resource_version"]
