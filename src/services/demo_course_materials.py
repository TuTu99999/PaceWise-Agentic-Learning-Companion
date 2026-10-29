"""Idempotent shared-course material catalog used by the PaceWise demo.

One source binary, extraction row, and vector namespace belongs to a course
resource version.  Enrollments only grant access; this module never creates
student-owned copies or writes material data into a learner workspace.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from src.course_source.db import SessionLocal as CourseSessionLocal
from src.course_source.learning_api import record_resource_version, resource_extension_payload
from src.course_source.models import (
    Course,
    CourseModule,
    ModuleItem,
    Resource,
    ResourceVersion,
)
from src.db import SessionLocal
from src.persistence_models import LmsFileIndex
from src.services.lms_files import file_version


@dataclass(frozen=True)
class CatalogEntry:
    course_code: str
    source_dir: str
    chapter: str
    filename: str


@dataclass(frozen=True)
class ExerciseCatalogEntry:
    course_code: str
    relative_path: str
    mixed_teacher_package: bool = False


# Only student-facing briefs belong here.  Teacher answer keys are deliberately
# excluded from the student RAG index.  The legacy OOPCPP201 Word file is also
# excluded because it contains embedded-systems exercises; the replacement
# below is a public, answer-free assignment brief built for this course.
EXERCISE_CATALOG: tuple[ExerciseCatalogEntry, ...] = (
    ExerciseCatalogEntry("DB201", "information-systems-analysis-design/course/database_systems/exercises/Co_So_Du_Lieu.docx"),
    ExerciseCatalogEntry("DSA201", "data_structures_and_algorithms/exercises/Cau_Truc_Du_Lieu_Va_Giai_Thuat.docx"),
    ExerciseCatalogEntry("OOPCPP201", "object_oriented_programming/exercises/Bai_tap_Cpp_theo_chuong.docx"),
    ExerciseCatalogEntry("WEB201", "web-application-development/exercises/bai_tap_theo_buoi.docx"),
    ExerciseCatalogEntry("RTOS301", "embedded-real-time-operating-systems/exercises/bai_tap_theo_buoi.docx"),
    ExerciseCatalogEntry("ISAD301", "information-systems-analysis-design/exercises/bai_tap_theo_buoi.docx"),
    ExerciseCatalogEntry("TEL201", "telecommunication-systems/exercises/bai_tap_theo_buoi.docx"),
    ExerciseCatalogEntry("OOPJAVA201", "oop/course/hoc_lieu_oop_day_du.docx", mixed_teacher_package=True),
)


def _entries(course_code: str, source_dir: str, chapters: list[tuple[str, tuple[str, ...]]]) -> list[CatalogEntry]:
    return [
        CatalogEntry(course_code, source_dir, chapter, filename)
        for chapter, filenames in chapters
        for filename in filenames
    ]


CATALOG: tuple[CatalogEntry, ...] = tuple(
    _entries("DB201", "information-systems-analysis-design/course/database_systems", [
        ("Chương 1: Khái quát về hệ cơ sở dữ liệu", ("Chuong01_Khai_quat_ve_cac_he_CSDL.pdf",)),
        ("Chương 2: Mô hình cơ sở dữ liệu", ("Chuong02_Mo_hinh_CSDL.pdf",)),
        ("Chương 3: Mô hình cơ sở dữ liệu quan hệ", ("Chuong03_Mo_hinh_CSDL_quan_he.pdf",)),
        ("Chương 4: Ngôn ngữ SQL", ("Chuong04a_SQL_Truy_van_du_lieu.pdf", "Chuong04b_SQL_Cap_nhat_DDL_Bao_mat.pdf")),
        ("Chương 5: Ràng buộc toàn vẹn", ("Chuong05_Rang_buoc_toan_ven.pdf",)),
        ("Chương 6: Phụ thuộc hàm và khóa", ("Chuong06_Phu_thuoc_ham_va_Khoa.pdf",)),
        ("Chương 7: Phân tách lược đồ quan hệ", ("Chuong07_Phan_tach.pdf",)),
        ("Chương 8: Chuẩn hóa cơ sở dữ liệu", ("Chuong08_Chuan_hoa.pdf",)),
        ("Chương 9: Phụ thuộc đa trị và phụ thuộc kết nối", ("Chuong09_Phu_thuoc_da_tri_va_ket_noi.pdf",)),
    ])
    + _entries("DSA201", "data_structures_and_algorithms", [
        ("Chương 1: Tổng quan cấu trúc dữ liệu và giải thuật", ("Buoi01_Tong_quan_CTDL_GT.pdf",)),
        ("Chương 2: Kỹ thuật tìm kiếm", ("Buoi02_Ky_thuat_tim_kiem.pdf",)),
        ("Chương 3: Sắp xếp đổi chỗ", ("Buoi03_Sap_xep_doi_cho.pdf",)),
        ("Chương 4: Sắp xếp chọn và chèn", ("Buoi04_Sap_xep_chon_va_chen.pdf",)),
        ("Chương 5: Sắp xếp trộn và sắp xếp ngoài", ("Buoi05_Sap_xep_tron_va_sap_xep_ngoai.pdf",)),
        ("Chương 6: Danh sách đặc", ("Buoi06_Danh_sach_dac.pdf",)),
        ("Chương 7: Danh sách liên kết đơn", ("Buoi07_Danh_sach_lien_ket_don.pdf",)),
        ("Chương 8: Danh sách liên kết kép", ("Buoi08_Danh_sach_lien_ket_kep.pdf",)),
        ("Chương 9: Ngăn xếp và hàng đợi", ("Buoi09_Ngan_xep_va_Hang_doi.pdf",)),
        ("Chương 10: Cây và cây nhị phân", ("Buoi10_Cay_va_cay_nhi_phan.pdf",)),
        ("Chương 11: Cây nhị phân tìm kiếm", ("Buoi11_Cay_nhi_phan_tim_kiem.pdf",)),
        ("Chương 12: Cây AVL và ôn tập", ("Buoi12_Cay_AVL_va_On_tap.pdf",)),
    ])
    + _entries("OOPCPP201", "object_oriented_programming", [
        ("Chương 1: Giới thiệu lập trình hướng đối tượng", ("Buoi01_Gioi_thieu_OOP.pdf",)),
        ("Chương 2: Mở rộng C++ phần 1", ("Buoi02_Mo_rong_Cpp_phan1.pdf",)),
        ("Chương 3: Mở rộng C++ phần 2", ("Buoi03_Mo_rong_Cpp_phan2.pdf",)),
        ("Chương 4: Lớp và đối tượng", ("Buoi04_Lop_va_doi_tuong.pdf",)),
        ("Chương 5: Constructor và Destructor", ("Buoi05_Constructor_Destructor.pdf",)),
        ("Chương 6: Thành viên đặc biệt", ("Buoi06_Thanh_vien_dac_biet.pdf",)),
        ("Chương 7: Đa năng hóa toán tử phần 1", ("Buoi07_Da_nang_hoa_toan_tu_phan1.pdf",)),
        ("Chương 8: Đa năng hóa toán tử phần 2", ("Buoi08_Da_nang_hoa_toan_tu_phan2.pdf",)),
        ("Chương 9: Tính kế thừa", ("Buoi09_Tinh_ke_thua.pdf",)),
        ("Chương 10: Tính đa hình", ("Buoi10_Tinh_da_hinh.pdf",)),
        ("Chương 11: Template và nhập xuất", ("Buoi11_Template_va_Nhap_xuat.pdf",)),
        ("Chương 12: Thiết kế chương trình hướng đối tượng", ("Buoi12_Thiet_ke_chuong_trinh_HDT.pdf",)),
    ])
    + _entries("WEB201", "web-application-development", [
        ("Chương 0: Giới thiệu môn học", ("00_gioi_thieu.pdf",)),
        ("Chương 1: Công nghệ Web", ("01_cong_nghe_web.pdf",)),
        ("Chương 2: HTML và CSS", ("02_1_html.pdf", "02_2_css.pdf")),
        ("Chương 3: JavaScript", ("03_javascript.pdf",)),
        ("Chương 4: Phát triển Web với PHP", ("04_php.pdf",)),
        ("Chương 5: PHP kết nối MySQL", ("05_php_mysql.pdf",)),
    ])
    + _entries("OOPJAVA201", "oop", [
        ("Chương 2: Introduction to OOP", ("02_introduction_to_oop.pdf",)),
        ("Chương 3: Java cơ bản", ("03_java.pdf",)),
        ("Chương 4: More Java", ("04_more_java.pdf",)),
        ("Chương 5: Inheritance", ("05_inheritance.pdf",)),
        ("Chương 6: Polymorphism", ("06_polymorphism.pdf",)),
        ("Chương 7: Exceptions", ("07_exceptions.pdf",)),
        ("Chương 9: Streams và cơ sở dữ liệu", ("09_1_streams.pdf", "09_2_co_so_du_lieu.pdf")),
        ("Chương 11: Template và Generics", ("11_template.pdf",)),
    ])
    + _entries("RTOS301", "embedded-real-time-operating-systems", [
        ("Chương 0: Giới thiệu môn học", ("00_gioi_thieu_mon_hoc.pdf",)),
        ("Chương 1: Tổng quan RTOS", ("01_tong_quan_rtos.pdf",)),
        ("Chương 2: Task, Queue và đồng bộ IPC", ("02_1_task_va_queue.pdf", "02_2_dong_bo_va_ipc.pdf")),
        ("Chương 3: Quản lý ngắt", ("03_quan_ly_ngat.pdf",)),
        ("Chương 4: Timer, bộ nhớ và I/O", ("04_1_software_timer.pdf", "04_2_quan_ly_bo_nho.pdf", "04_3_io_management.pdf")),
        ("Chương 5: Troubleshooting và Debugging", ("05_troubleshooting_debugging.pdf",)),
    ])
    + _entries("ISAD301", "information-systems-analysis-design", [
        ("Chương 1: Tổng quan phân tích thiết kế hệ thống", ("01_tong_quan_pttkhttt.pdf",)),
        ("Chương 2: Giới thiệu UML", ("02_gioi_thieu_uml.pdf",)),
        ("Chương 3: Biểu đồ Use Case", ("03_bieu_do_use_case.pdf",)),
        ("Chương 4: Biểu đồ lớp", ("04_bieu_do_lop.pdf",)),
        ("Chương 5: Biểu đồ tương tác", ("05_bieu_do_tuong_tac.pdf",)),
        ("Chương 6: Biểu đồ trạng thái", ("06_bieu_do_trang_thai.pdf",)),
    ])
    + _entries("TEL201", "telecommunication-systems", [
        ("Chương 1: Tổng quan hệ thống viễn thông", ("01_tong_quan_he_thong_vien_thong.pdf",)),
        ("Chương 2: Cơ sở kỹ thuật chuyển mạch", ("02_co_so_ky_thuat_chuyen_mach.pdf",)),
        ("Chương 3: Hệ thống thông tin tương tự", ("03_he_thong_thong_tin_tuong_tu.pdf",)),
        ("Chương 4: Hệ thống truyền dẫn số", ("04_he_thong_truyen_dan_so.pdf",)),
        ("Chương 5: Hệ thống thông tin quang", ("05_he_thong_thong_tin_quang.pdf",)),
        ("Chương 6: Thông tin vô tuyến", ("06_thong_tin_vo_tuyen.pdf",)),
    ])
)


def validate_catalog(material_root: Path, entries: tuple[CatalogEntry, ...] = CATALOG) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    errors: list[dict] = []
    for entry in entries:
        identity = (entry.course_code, entry.chapter, entry.filename)
        path = material_root / entry.source_dir / "slides" / entry.filename
        if identity in seen:
            errors.append({"entry": asdict(entry), "error": "duplicate_catalog_entry"})
        elif not path.is_file():
            errors.append({"entry": asdict(entry), "error": "missing_file", "path": str(path)})
        elif path.stat().st_size <= 5 or path.read_bytes()[:5] != b"%PDF-":
            errors.append({"entry": asdict(entry), "error": "invalid_pdf", "path": str(path)})
        seen.add(identity)
    return errors


def validate_exercise_catalog(
    material_root: Path,
    entries: tuple[ExerciseCatalogEntry, ...] = EXERCISE_CATALOG,
) -> list[dict]:
    errors: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        identity = (entry.course_code, entry.relative_path)
        path = material_root / entry.relative_path
        if identity in seen:
            errors.append({"entry": asdict(entry), "error": "duplicate_catalog_entry"})
        elif not path.is_file():
            errors.append({"entry": asdict(entry), "error": "missing_file", "path": str(path)})
        else:
            try:
                with zipfile.ZipFile(path) as archive:
                    if "word/document.xml" not in archive.namelist():
                        raise ValueError("word/document.xml missing")
            except (ValueError, zipfile.BadZipFile) as exc:
                errors.append({"entry": asdict(entry), "error": "invalid_docx", "detail": str(exc)})
        seen.add(identity)
    return errors


def _fold_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.replace("Đ", "D").replace("đ", "d"))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _keywords(value: str) -> set[str]:
    ignored = {"bai", "tap", "chuong", "buoi", "mon", "va", "cho", "cua", "phan", "the", "with"}
    return {token for token in _fold_text(value).split() if len(token) > 2 and token not in ignored}


def _docx_paragraphs(path: Path) -> list[str]:
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def _exercise_sections(path: Path) -> list[dict]:
    sections: list[dict] = []
    current: dict | None = None
    paragraphs = _docx_paragraphs(path)
    # A combined teacher package may contain a syllabus, student exercises and
    # answer keys.  Start at the explicit exercise boundary and stop before
    # exams/solutions so private content never enters planning evidence.
    exercise_marker = next(
        (index for index, paragraph in enumerate(paragraphs) if _fold_text(paragraph) == "bai tap theo buoi"),
        None,
    )
    if exercise_marker is not None:
        paragraphs = paragraphs[exercise_marker + 1 :]
    for paragraph in paragraphs:
        folded = _fold_text(paragraph)
        if exercise_marker is not None and (
            folded.startswith("kiem tra giua ky")
            or folded.startswith("de giua ky")
            or folded.startswith("dap an")
            or folded.startswith("kiem tra cuoi ky")
            or folded.startswith("de cuoi ky")
        ):
            break
        heading = re.match(r"^Buổi\s+(\d+)\s*[–—-]?\s*(.+)$", paragraph, flags=re.IGNORECASE)
        if heading:
            if current:
                sections.append(current)
            current = {"number": int(heading.group(1)), "title": heading.group(2).strip(), "body": [], "criteria": []}
            continue
        if current is None:
            continue
        rubric = re.match(r"^Rubric\s+\d+\s*điểm\s*:\s*(.+)$", paragraph, flags=re.IGNORECASE)
        if rubric:
            for index, raw in enumerate(rubric.group(1).split(";"), start=1):
                raw = raw.strip().rstrip(".")
                match = re.match(r"(.+?)\s+(\d+(?:[.,]\d+)?)$", raw)
                if match:
                    current["criteria"].append(
                        {"name": match.group(1).strip(), "points": float(match.group(2).replace(",", "."))}
                    )
                elif raw:
                    current["criteria"].append({"name": raw, "points": 1.0})
        else:
            current["body"].append(paragraph)
    if current:
        sections.append(current)
    return sections


def matching_exercise_sections(module_name: str, sections: list[dict]) -> list[dict]:
    query = _keywords(module_name)
    chapter = re.search(r"chương\s+(\d+)", module_name, flags=re.IGNORECASE)
    # Broad labels such as "phụ thuộc" or "mô hình" are not enough when the
    # chapter also names a specific subtype. Requiring more of a long query
    # prevents "phụ thuộc đa trị" from being mapped to an unrelated
    # "phụ thuộc hàm" exercise merely because both share two generic words.
    minimum_title_score = 0.50 if len(query) >= 4 else 0.30
    ranked: list[tuple[float, dict]] = []
    title_matches: list[dict] = []
    title_scores: dict[int, float] = {}
    for section in sections:
        title_tokens = _keywords(section["title"])
        body_tokens = _keywords(" ".join(section["body"][:1]))
        title_score = len(query & title_tokens) / max(1, len(query))
        body_score = len(query & body_tokens) / max(1, len(query))
        score = title_score + 0.15 * body_score
        title_scores[section["number"]] = title_score
        if title_score >= minimum_title_score or (title_score >= 0.20 and score >= minimum_title_score):
            ranked.append((score, section))
        if title_score >= minimum_title_score:
            title_matches.append(section)
    # The imported schedule is authoritative about the chapter number.  A
    # shared exercise book often repeats broad words such as "mô hình" in
    # adjacent chapters; expanding that lexical match used to attach questions
    # from chapters 3-4 to a chapter-2 assignment.  Prefer the numbered section
    # whenever it is at least a plausible title match, then use fuzzy ranges
    # only for modules without a usable chapter number.
    if chapter:
        number = int(chapter.group(1))
        exact = next((item for item in sections if item["number"] == number), None)
        best_title_score = max(title_scores.values(), default=0.0)
        if exact and title_scores.get(number, 0.0) >= max(minimum_title_score, best_title_score * 0.70):
            return [exact]
    if len(title_matches) >= 2:
        first = min(item["number"] for item in title_matches)
        last = max(item["number"] for item in title_matches)
        if last - first <= 3:
            return [item for item in sections if first <= item["number"] <= last]
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["number"]))
    if not ranked:
        # A chapter number and an exercise-session number are not universally
        # equivalent (for example, one SQL chapter may span three sessions).
        # No semantic match is safer than scheduling the same ordinal section.
        return []
    best = ranked[0][0] if ranked else 0
    return [section for score, section in ranked if score >= max(minimum_title_score, best * 0.55)][:4]


def _copy_once(source: Path, upload_dir: Path, course_id: int, checksum: str) -> tuple[Path, bool]:
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()
    target = upload_dir / f"course-{course_id}-{checksum}{suffix}"
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
            raise RuntimeError(f"Shared material target checksum mismatch: {target}")
        return target, False
    temporary = upload_dir / f".{target.name}.{uuid4().hex}.tmp"
    try:
        with source.open("rb") as input_file, temporary.open("xb") as output_file:
            shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != checksum:
            raise RuntimeError(f"Copied material checksum mismatch: {source}")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target, True


def _copy_bytes_once(data: bytes, upload_dir: Path, course_id: int, checksum: str, suffix: str) -> tuple[Path, bool]:
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / f"course-{course_id}-{checksum}{suffix}"
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
            raise RuntimeError(f"Shared material target checksum mismatch: {target}")
        return target, False
    temporary = upload_dir / f".{target.name}.{uuid4().hex}.tmp"
    try:
        temporary.write_bytes(data)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != checksum:
            raise RuntimeError("Generated student material checksum mismatch")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target, True


def _student_exercise_markdown(title: str, sections: list[dict]) -> bytes:
    lines = [f"# {title}", ""]
    for section in sections:
        lines.extend((f"## Buổi {section['number']} — {section['title']}", ""))
        lines.extend(str(value) for value in section.get("body") or [])
        criteria = section.get("criteria") or []
        if criteria:
            lines.extend(("", "### Rubric công khai", ""))
            lines.extend(f"- {item['name']}: {item['points']:g} điểm" for item in criteria)
        lines.append("")
    return "\n".join(lines).encode("utf-8")


def _existing_course_resource(db, course_id: int, checksum: str) -> Resource | None:
    return db.scalar(
        select(Resource)
        .join(ResourceVersion, ResourceVersion.resource_id == Resource.id)
        .where(Resource.course_id == course_id, ResourceVersion.checksum_sha256 == checksum)
        .order_by(ResourceVersion.version.desc())
        .limit(1)
    )


def _link_resource_to_module(db, module: CourseModule, resource: Resource) -> bool:
    existing = db.scalar(
        select(ModuleItem).where(
            ModuleItem.module_id == module.id,
            ModuleItem.item_type == "resource",
            ModuleItem.content_id == resource.id,
        )
    )
    if existing:
        return False
    position = len(db.scalars(select(ModuleItem).where(ModuleItem.module_id == module.id)).all()) + 1
    db.add(
        ModuleItem(
            module_id=module.id,
            title=resource.title,
            item_type="resource",
            content_id=resource.id,
            published=True,
            position=position,
        )
    )
    return True


def _existing_resource(db, course_id: int, chapter: str, checksum: str) -> Resource | None:
    return db.scalar(
        select(Resource)
        .join(ResourceVersion, ResourceVersion.resource_id == Resource.id)
        .join(ModuleItem, (ModuleItem.content_id == Resource.id) & (ModuleItem.item_type == "resource"))
        .join(CourseModule, CourseModule.id == ModuleItem.module_id)
        .where(
            Resource.course_id == course_id,
            CourseModule.course_id == course_id,
            CourseModule.name == chapter,
            ResourceVersion.checksum_sha256 == checksum,
        )
        .order_by(ResourceVersion.version.desc())
        .limit(1)
    )


def _ensure_index(institution_id: str, course_id: int, course_code: str, resource: Resource, metadata: dict) -> str:
    item = {"id": resource.id, "title": resource.title, "kind": resource.kind, "source_url": resource.source_url, **metadata}
    version = file_version(item)
    identifier = f"{institution_id}:{course_id}:{resource.id}"
    with SessionLocal() as db:
        row = db.get(LmsFileIndex, identifier)
        if row and row.resource_version == version and row.status not in {"delete_pending", "unavailable"}:
            # Metadata such as the authoritative chapter may improve planning
            # without changing the binary or forcing an expensive re-embed.
            row.metadata_json = json.dumps({**item, "course_code": course_code}, ensure_ascii=False)
            db.commit()
            return "unchanged"
        row = row or LmsFileIndex(
            id=identifier,
            institution_id=institution_id,
            course_id=course_id,
            file_id=resource.id,
        )
        row.resource_version = version
        row.metadata_json = json.dumps({**item, "course_code": course_code}, ensure_ascii=False)
        row.chunks_json = "[]"
        row.status = "queued"
        row.attempts = 0
        row.last_error = ""
        db.add(row)
        db.commit()
    return "queued"


def load_shared_exercises(
    material_root: Path,
    upload_dir: Path,
    institution_id: str,
    *,
    entries: tuple[ExerciseCatalogEntry, ...] = EXERCISE_CATALOG,
    strict_courses: bool = True,
) -> dict:
    """Load student exercise briefs once per course without changing assignments.

    The resource is placed in one dedicated module.  This deliberately avoids
    bulk-attaching a broad exercise book to every chapter or overwriting a
    teacher-authored assignment/rubric.
    """
    errors = validate_exercise_catalog(material_root, entries)
    if errors:
        raise ValueError(json.dumps(errors, ensure_ascii=False))
    with CourseSessionLocal() as db:
        courses = {course.code: course for course in db.scalars(select(Course)).all()}
    missing_courses = sorted({entry.course_code for entry in entries} - courses.keys())
    if missing_courses and strict_courses:
        raise ValueError("Missing courses: " + ", ".join(missing_courses))

    counts = {"created": 0, "unchanged": 0, "queued": 0, "binaryCreated": 0, "skippedMissingCourse": 0}
    items: list[dict] = []
    for entry in entries:
        course = courses.get(entry.course_code)
        if course is None:
            counts["skippedMissingCourse"] += 1
            continue
        source = material_root / entry.relative_path
        sections = _exercise_sections(source)
        if not sections:
            raise ValueError(f"No student exercise sections found: {source}")
        if entry.mixed_teacher_package:
            public_bytes = _student_exercise_markdown(f"Bài tập theo chương · {entry.course_code}", sections)
            checksum = hashlib.sha256(public_bytes).hexdigest()
            resource_title = f"{source.stem}_ban_sinh_vien.md"
            content_type = "text/markdown"
        else:
            public_bytes = None
            checksum = hashlib.sha256(source.read_bytes()).hexdigest()
            resource_title = source.name
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        with CourseSessionLocal() as db:
            resource = _existing_course_resource(db, course.id, checksum)
            created = resource is None
            target, copied = (
                _copy_bytes_once(public_bytes, upload_dir, course.id, checksum, ".md")
                if public_bytes is not None
                else _copy_once(source, upload_dir, course.id, checksum)
            )
            if created:
                resource = Resource(
                    course_id=course.id,
                    title=resource_title,
                    kind="assignment_guide",
                    source_url=f"/api/files/{target.name}",
                )
                db.add(resource)
                db.flush()
                record_resource_version(
                    db,
                    resource,
                    checksum=checksum,
                    size_bytes=len(public_bytes) if public_bytes is not None else source.stat().st_size,
                    content_type=content_type,
                )
                module = db.scalar(
                    select(CourseModule).where(
                        CourseModule.course_id == course.id,
                        CourseModule.name == "Bài tập theo chương",
                    )
                )
                if module is None:
                    module = CourseModule(course_id=course.id, name="Bài tập theo chương", published=True)
                    db.add(module)
                    db.flush()
                _link_resource_to_module(db, module, resource)
                counts["created"] += 1
            else:
                counts["unchanged"] += 1
            db.commit()
            if copied:
                counts["binaryCreated"] += 1
            metadata = {
                **resource_extension_payload(db, resource),
                "planning_sections": sections,
                "content_role": "student_assignment_brief",
            }
            resource_id = resource.id
        index_state = _ensure_index(institution_id, course.id, course.code, resource, metadata)
        if index_state == "queued":
            counts["queued"] += 1
        items.append(
            {
                "courseCode": entry.course_code,
                "filename": resource_title,
                "resourceId": resource_id,
                "sectionCount": len(sections),
                "indexState": index_state,
            }
        )
    return {"catalogFiles": len(entries), "missingCourses": missing_courses, "counts": counts, "items": items}


def load_shared_catalog(
    material_root: Path,
    upload_dir: Path,
    institution_id: str,
    *,
    entries: tuple[CatalogEntry, ...] = CATALOG,
    strict_courses: bool = True,
) -> dict:
    errors = validate_catalog(material_root, entries)
    if errors:
        raise ValueError(json.dumps(errors, ensure_ascii=False))

    with CourseSessionLocal() as db:
        courses = {course.code: course for course in db.scalars(select(Course)).all()}
    missing_courses = sorted({entry.course_code for entry in entries} - courses.keys())
    if missing_courses and strict_courses:
        raise ValueError("Missing courses: " + ", ".join(missing_courses))

    counts = {"created": 0, "unchanged": 0, "queued": 0, "binaryCreated": 0, "skippedMissingCourse": 0}
    items: list[dict] = []
    for entry in entries:
        course = courses.get(entry.course_code)
        if course is None:
            counts["skippedMissingCourse"] += 1
            continue
        source = material_root / entry.source_dir / "slides" / entry.filename
        checksum = hashlib.sha256(source.read_bytes()).hexdigest()
        with CourseSessionLocal() as db:
            resource = _existing_resource(db, course.id, entry.chapter, checksum)
            created = resource is None
            target, copied = _copy_once(source, upload_dir, course.id, checksum)
            if created:
                resource = Resource(
                    course_id=course.id,
                    title=entry.filename,
                    kind="slides",
                    source_url=f"/api/files/{target.name}",
                )
                db.add(resource)
                db.flush()
                module = db.scalar(
                    select(CourseModule).where(
                        CourseModule.course_id == course.id,
                        CourseModule.name == entry.chapter,
                    )
                )
                if module is None:
                    module = CourseModule(course_id=course.id, name=entry.chapter, published=True)
                    db.add(module)
                    db.flush()
                db.add(
                    ModuleItem(
                        module_id=module.id,
                        title=entry.filename,
                        item_type="resource",
                        content_id=resource.id,
                        published=True,
                        position=(
                            len(db.scalars(select(ModuleItem).where(ModuleItem.module_id == module.id)).all()) + 1
                        ),
                    )
                )
                record_resource_version(
                    db,
                    resource,
                    checksum=checksum,
                    size_bytes=source.stat().st_size,
                    content_type="application/pdf",
                )
                db.commit()
                counts["created"] += 1
            else:
                counts["unchanged"] += 1
            if copied:
                counts["binaryCreated"] += 1
            metadata = {
                **resource_extension_payload(db, resource),
                "content_role": "learning_material",
                "planning_chapter": entry.chapter,
            }
            resource_id = resource.id
        index_state = _ensure_index(institution_id, course.id, course.code, resource, metadata)
        if index_state == "queued":
            counts["queued"] += 1
        items.append(
            {
                "courseCode": entry.course_code,
                "courseId": course.id,
                "chapter": entry.chapter,
                "filename": entry.filename,
                "resourceId": resource_id,
                "checksum": checksum,
                "indexState": index_state,
            }
        )
    exercises = load_shared_exercises(
        material_root,
        upload_dir,
        institution_id,
        strict_courses=strict_courses,
    )
    return {
        "architecture": {
            "binaryOwnership": "course_resource_version",
            "indexOwnership": "institution_course_resource_version",
            "studentCopies": 0,
        },
        "catalogFiles": len(entries),
        "courses": sorted(courses.keys() & {entry.course_code for entry in entries}),
        "missingCourses": missing_courses,
        "counts": counts,
        "items": items,
        "exercises": exercises,
    }
