import io
import zipfile

from src.api.routes import _assignment_planning_candidates, _planning_sections_from_chunks
from src.services.document_roles import filter_student_chunks
from src.services.material_service import extract_text_from_docx


def docx_bytes(paragraphs):
    body = "".join(
        f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>' for text in paragraphs
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body>{body}</w:body></w:document>'
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", document)
    return output.getvalue()


def test_mixed_word_package_excludes_answer_sections_and_keeps_public_rubric():
    data = docx_bytes([
        "Bài tập theo buổi",
        "Buổi 1 – Class và object",
        "Tạo class Student và viết test cho invariant.",
        "Rubric 100 điểm: đúng nghiệp vụ 60; test 40.",
        "Đáp án và rubric giữa kỳ",
        "Mã nguồn hoàn chỉnh bí mật của giảng viên.",
        "Rubric chung cho bài lập trình",
        "Tính đúng 60; kiểm thử 40.",
    ])
    _, chunks = extract_text_from_docx(data, "oop.docx")
    visible, excluded = filter_student_chunks(chunks, "mixed_assignment_package")
    text = "\n".join(item["content"] for item in visible)

    assert excluded > 0
    assert "Mã nguồn hoàn chỉnh" not in text
    assert "Tạo class Student" in text
    assert "Rubric chung" in text
    assert all(item["student_visible"] for item in visible)


def test_teacher_solution_never_produces_student_chunks():
    visible, excluded = filter_student_chunks([{"content": "secret"}], "teacher_solution")
    assert visible == [] and excluded == 1


def test_plan_groups_only_student_visible_indexed_word_sections():
    sections = _planning_sections_from_chunks(
        '[{"section_title":"Buổi 1 – Class","content":"Tạo class Student",'
        '"student_visible":true},{"section_title":"Buổi 1 – Class",'
        '"content":"Viết unit test","student_visible":true},{"section_title":"Đáp án",'
        '"content":"Mã nguồn bí mật","student_visible":false}]'
    )

    assert sections == [{
        "number": 1,
        "title": "Buổi 1 – Class",
        "body": ["Tạo class Student", "Viết unit test"],
        "criteria": [],
    }]


def test_plan_prefers_word_brief_and_uses_exact_chapter_slide_only_as_fallback():
    word = {"number": 1, "title": "Chương 1: OOP và class", "body": ["Viết class"], "criteria": []}
    slide = {"number": 1, "title": "Khái niệm class", "body": ["Class và object"], "criteria": []}
    unrelated = {"number": 2, "title": "SQL", "body": ["SELECT"], "criteria": []}
    briefs = {"37": [("file:word", [word])]}
    slides = {"37": [
        ("file:slide", "Chương 1: OOP", [slide]),
        ("file:wrong", "Chương 2: SQL", [unrelated]),
    ]}

    selected, source = _assignment_planning_candidates("Chương 1: OOP", "37", briefs, slides)
    assert selected == [("file:word", word)]
    assert source == "assignment_brief"

    selected, source = _assignment_planning_candidates("Chương 1: OOP", "37", {}, slides)
    assert selected == [("file:slide", slide)]
    assert source == "chapter_material"
