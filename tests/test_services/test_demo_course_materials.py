import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from src.services.demo_course_materials import (
    CATALOG,
    EXERCISE_CATALOG,
    _docx_paragraphs,
    _exercise_sections,
    matching_exercise_sections,
    validate_catalog,
    validate_exercise_catalog,
)


def _write_docx(path: Path, paragraphs: list[str]) -> None:
    """Create the minimal DOCX shape consumed by the catalog parser."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(
        f"<w:p><w:r><w:t>{escape(paragraph)}</w:t></w:r></w:p>" for paragraph in paragraphs
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document.encode("utf-8"))


def _catalog_fixture(root: Path) -> Path:
    for entry in CATALOG:
        path = root / entry.source_dir / "slides" / entry.filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4\n%%EOF\n")
    for entry in EXERCISE_CATALOG:
        _write_docx(root / entry.relative_path, ["Student exercise brief"])
    return root


def _exercise_paragraphs(*, title_for_second: str = "Task, Queue và đồng bộ IPC") -> list[str]:
    paragraphs = ["Lập trình OOP", "Bài tập theo buổi"]
    for number in range(1, 13):
        title = title_for_second if number == 2 else f"Chủ đề {number}"
        paragraphs.extend(
            [
                f"Buổi {number} — {title}",
                f"Thực hành nội dung {number}",
                "Rubric 10 điểm: Đúng yêu cầu 6; Giải thích 4",
            ]
        )
    paragraphs.extend(["Đáp án và rubric", "Nội dung giáo viên không được lập chỉ mục"])
    return paragraphs


def test_catalog_maps_all_eight_courses_and_every_pdf_once():
    assert {entry.course_code for entry in CATALOG} == {
        "DB201", "DSA201", "OOPCPP201", "WEB201", "OOPJAVA201", "RTOS301", "ISAD301", "TEL201"
    }
    identities = {(entry.course_code, entry.chapter, entry.filename) for entry in CATALOG}
    assert len(identities) == len(CATALOG) == 71


def test_demo_pdf_catalog_accepts_a_complete_release_pack(tmp_path):
    root = _catalog_fixture(tmp_path)
    assert validate_catalog(root) == []


def test_catalog_validator_fails_closed_for_missing_file(tmp_path):
    assert validate_catalog(tmp_path, (CATALOG[0],))[0]["error"] == "missing_file"


def test_student_exercise_catalog_is_valid_and_excludes_answer_keys(tmp_path):
    root = _catalog_fixture(tmp_path)
    assert validate_exercise_catalog(root) == []
    assert len(EXERCISE_CATALOG) == 7
    assert all("dap_an" not in entry.relative_path.lower() for entry in EXERCISE_CATALOG)


def test_oop_supplemental_documents_fail_closed_instead_of_polluting_student_rag(tmp_path):
    indexed_exercise_courses = {entry.course_code for entry in EXERCISE_CATALOG}
    assert "OOPCPP201" not in indexed_exercise_courses
    assert "OOPJAVA201" in indexed_exercise_courses

    java_entry = next(item for item in EXERCISE_CATALOG if item.course_code == "OOPJAVA201")
    java_path = tmp_path / java_entry.relative_path
    _write_docx(java_path, _exercise_paragraphs())
    java_course = _docx_paragraphs(java_path)

    assert "Lập trình OOP" in java_course[0]
    assert any("Bài tập theo buổi" in paragraph for paragraph in java_course)
    # The otherwise complete Java document also contains instructor answer
    # sections, so exposing the whole binary to student retrieval is unsafe.
    assert any("Đáp án và rubric" in paragraph for paragraph in java_course)

    java_sections = _exercise_sections(java_path)
    assert len(java_sections) == 12
    assert all("đáp án" not in " ".join(item["body"]).casefold() for item in java_sections)
    assert all(item["criteria"] for item in java_sections)


def test_exercise_parser_and_chapter_match_keep_rubric_evidence(tmp_path):
    path = tmp_path / "exercise.docx"
    _write_docx(path, _exercise_paragraphs(title_for_second="Producer Consumer với Task, Queue và đồng bộ IPC"))
    sections = _exercise_sections(path)

    matches = matching_exercise_sections("Chương 2: Task, Queue và đồng bộ IPC", sections)

    assert len(sections) == 12
    assert any("Producer" in item["title"] for item in matches)
    assert all(item["criteria"] for item in matches)
