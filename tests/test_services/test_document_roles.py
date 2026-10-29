import io
import json
import zipfile

from src.api.routes import (
    _assignment_parts_from_section,
    _assignment_planning_candidates,
    _brief_matches_course,
    _deduplicate_assignment_parts,
    _planning_exercise_sections_from_chunks,
    _planning_sections_from_chunks,
)
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


def test_uploaded_exercise_book_keeps_buoi_numbers_and_rubrics():
    chunks = [
        {"section_title": "BÀI TẬP MÔN CƠ SỞ DỮ LIỆU", "content": "BÀI TẬP MÔN CƠ SỞ DỮ LIỆU"},
        {
            "section_title": "Buổi 1 – Khái quát hệ CSDL",
            "content": "Buổi 1 – Khái quát hệ CSDL\nPhân tích kiến trúc ba mức.\nSản phẩm nộp: sơ đồ.",
        },
        {"section_title": "Rubric 100 điểm: Kiến trúc 60; Trình bày 40.", "content": "Rubric 100 điểm: Kiến trúc 60; Trình bày 40."},
        {
            "section_title": "Buổi 2 – Mô hình thực thể liên kết",
            "content": "Buổi 2 – Mô hình thực thể liên kết\nVẽ ERD cho bài toán.",
        },
    ]

    sections = _planning_exercise_sections_from_chunks(json.dumps(chunks, ensure_ascii=False))

    assert [item["number"] for item in sections] == [1, 2]
    assert sections[0]["title"] == "Khái quát hệ CSDL"
    assert sections[0]["criteria"] == [
        {"name": "Kiến trúc", "points": 60.0},
        {"name": "Trình bày", "points": 40.0},
    ]


def test_explicit_document_subject_mismatch_is_not_planning_evidence():
    sections = [{
        "number": 1,
        "title": "BÀI TẬP MÔN CƠ SỞ DỮ LIỆU",
        "body": ["Bài ôn tập và thực hành theo 12 buổi"],
        "criteria": [],
    }]

    assert _brief_matches_course(sections, "Hệ cơ sở dữ liệu") is True
    assert _brief_matches_course(sections, "Nhập môn lập trình Python") is False


def test_plan_prefers_word_brief_and_uses_exact_chapter_slide_only_as_fallback():
    word = {"number": 1, "title": "Chương 1: OOP và class", "body": ["Viết class"], "criteria": []}
    slide = {"number": 1, "title": "Khái niệm class", "body": ["Class và object"], "criteria": []}
    unrelated = {"number": 2, "title": "SQL", "body": ["SELECT"], "criteria": []}
    briefs = {"37": [("file:word", "Chương 1: OOP", [word])]}
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


def test_plan_uses_only_the_exact_chapter_brief_before_generic_or_other_chapters():
    generic = {"number": 3, "title": "Sắp xếp đổi chỗ", "body": ["Câu chung"], "criteria": []}
    chapter_three = {"number": 3, "title": "Sắp xếp đổi chỗ", "body": ["Câu chương 3"], "criteria": []}
    chapter_four = {"number": 3, "title": "Sắp xếp đổi chỗ", "body": ["Câu sai từ file chương 4"], "criteria": []}
    briefs = {"36": [
        ("file:generic", "", [generic]),
        ("file:chapter-3", "Chương 3: Sắp xếp đổi chỗ", [chapter_three]),
        ("file:chapter-4", "Chương 4: Sắp xếp chọn và chèn", [chapter_four]),
    ]}

    selected, source = _assignment_planning_candidates(
        "Chương 3: Sắp xếp đổi chỗ", "36", briefs, {}
    )

    assert selected == [("file:chapter-3", chapter_three)]
    assert source == "assignment_brief"

    slide = {"number": 3, "title": "Sắp xếp đổi chỗ", "body": ["Nội dung chương 3"], "criteria": []}
    selected, source = _assignment_planning_candidates(
        "Chương 3: Sắp xếp đổi chỗ",
        "36",
        {"36": [("file:chapter-4", "Chương 4: Sắp xếp chọn và chèn", [chapter_four])]},
        {"36": [("file:slide-3", "Chương 3: Sắp xếp đổi chỗ", [slide])]},
    )

    assert selected == [("file:slide-3", slide)]
    assert source == "chapter_material"


def test_assignment_brief_extracts_numbered_questions_with_stable_sources():
    parts = _assignment_parts_from_section(
        {
            "number": 3,
            "title": "Bài tập SQL",
            "body": [
                "Câu 1. Viết truy vấn tìm sinh viên có điểm lớn nhất.",
                "Câu 2. Viết truy vấn thống kê số sinh viên theo lớp.",
                "Câu 3. Giải thích kế hoạch thực thi của câu 2.",
            ],
        },
        "file:42#exercise=3",
    )

    assert [item["partId"] for item in parts] == ["file-42-S3-P1", "file-42-S3-P2", "file-42-S3-P3"]
    assert parts[0]["label"] == "Câu 1"
    assert parts[2]["sourceRef"] == "file:42#exercise=3&part=file-42-S3-P3"


def test_duplicate_assignment_files_do_not_repeat_the_same_work_items():
    first = _assignment_parts_from_section(
        {
            "number": 3,
            "title": "Bài tập chương 3",
            "body": ["Câu 1.1: Phân tích dữ liệu. Câu 1.2: Cài đặt thuật toán."],
        },
        "file:first#exercise=3",
    )
    duplicate = _assignment_parts_from_section(
        {
            "number": 3,
            "title": "Bài tập chương 3",
            "body": ["Câu 1.1: Phân tích dữ liệu. Câu 1.2: Cài đặt thuật toán."],
        },
        "file:duplicate#exercise=3",
    )

    result = _deduplicate_assignment_parts([*first, *duplicate])

    assert [item["label"] for item in result] == ["Câu 1.1", "Câu 1.2"]
    assert [item["partId"] for item in result] == ["file-first-S3-P1", "file-first-S3-P2"]


def test_repeated_part_id_is_removed_even_when_indexed_text_changes_slightly():
    result = _deduplicate_assignment_parts([
        {"partId": "file-1-S3-P1", "label": "Câu 1", "content": "Nội dung gốc"},
        {"partId": "file-1-S3-P1", "label": "Câu 1", "content": "Nội dung gốc."},
    ])

    assert result == [{"partId": "file-1-S3-P1", "label": "Câu 1", "content": "Nội dung gốc"}]


def test_project_brief_extracts_inline_requirements_with_project_labels():
    parts = _assignment_parts_from_section(
        {
            "number": 5,
            "title": "Project Web bán hàng",
            "body": [
                "Yêu cầu 1: Thiết kế cơ sở dữ liệu. "
                "Yêu cầu 2: Xây dựng API đăng nhập và sản phẩm. "
                "Yêu cầu 3: Xây dựng giao diện và tích hợp API. "
                "Yêu cầu 4: Viết kiểm thử và báo cáo."
            ],
        },
        "file:84#exercise=5",
    )

    assert [item["label"] for item in parts] == [
        "Yêu cầu 1",
        "Yêu cầu 2",
        "Yêu cầu 3",
        "Yêu cầu 4",
    ]
    assert [item["partId"] for item in parts] == [
        "file-84-S5-P1",
        "file-84-S5-P2",
        "file-84-S5-P3",
        "file-84-S5-P4",
    ]


def test_project_brief_uses_neutral_part_labels_for_separate_bullets():
    parts = _assignment_parts_from_section(
        {
            "number": 2,
            "title": "Project API",
            "body": [
                "Thiết kế mô hình dữ liệu và migration.",
                "Xây dựng API và kiểm thử tích hợp.",
            ],
        },
        "file:85#exercise=2",
    )

    assert [item["label"] for item in parts] == [
        "Project API · Phần 1",
        "Project API · Phần 2",
    ]


def test_assignment_brief_names_submission_step_instead_of_repeating_part_number():
    parts = _assignment_parts_from_section(
        {
            "number": 2,
            "title": "Mô hình cơ sở dữ liệu",
            "body": [
                "Xác định thực thể, thuộc tính, khóa và các mối quan hệ.",
                "Sản phẩm nộp: sơ đồ ERD và phần giải thích quyết định.",
            ],
        },
        "file:118#exercise=2",
    )

    assert [item["label"] for item in parts] == [
        "Mô hình cơ sở dữ liệu · Phần 1",
        "Sản phẩm nộp · Mô hình cơ sở dữ liệu",
    ]
