"""
Dịch vụ trích xuất nội dung tài liệu học tập đa định dạng (PDF, DOCX, PPTX, TXT)
và lập chỉ mục vector tức thời vào Qdrant Vector Store.
"""

from __future__ import annotations

import io
import logging
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from src.agents.tools.qdrant_retriever import (
    DEFAULT_COLLECTION_NAME,
    EMBEDDING_DIM,
    _get_embedding_model,
    _get_qdrant_client,
    clear_retrieval_cache,
)
from src.persistence_models import CourseMaterial

logger = logging.getLogger("pacewise.materials")


def _clean_text(text: str) -> str:
    """Loại bỏ ký tự thừa, chuẩn hóa khoảng trắng, lọc sạch surrogates và null bytes cho PostgreSQL UTF-8."""
    if not text:
        return ""
    # 1. Loại bỏ null byte \x00 (PostgreSQL không cho phép null byte trong chuỗi TEXT)
    cleaned = text.replace("\x00", "")
    # 2. Loại bỏ các mã surrogate \ud800-\udfff (gây lỗi UnicodeEncodeError khi psycopg ghi UTF-8)
    cleaned = re.sub(r"[\ud800-\udfff]", "", cleaned)
    # 3. Chuẩn hóa khoảng trắng và dấu xuống dòng
    return re.sub(r"[ \t]+", " ", re.sub(r"\r\n|\r", "\n", cleaned)).strip()


def _detect_heading(line: str) -> str | None:
    """Nhận diện xem 1 dòng có phải là tiêu đề mục/chương/phần hay không."""
    s = line.strip()
    if not s or len(s) > 100:
        return None
    # Dạng markdown heading: # Heading, ## Heading...
    m = re.match(r"^#{1,6}\s+(.+)$", s)
    if m:
        return m.group(1).strip()
    # Dạng: Mục 1, Chương 2, Buổi 3, Câu 4, Section 1, Chapter 2
    if re.match(r"^(mục|chương|phần|bài|buổi|câu|tiểu mục|section|chapter|part)\s+\d+[:\.\-–—]?\s*.+", s, re.IGNORECASE):
        return s
    if re.match(r"^(bài tập|đề bài|kiểm tra|đề (giữa|cuối) kỳ|đáp án|lời giải|rubric|tiêu chí chấm|answer key)\b", s, re.IGNORECASE):
        return s
    # Dạng: 1.1, 1.2, 2.1...
    if re.match(r"^\d+(\.\d+)+\.?\s+[A-ZÀ-Ỹ0-9].+", s):
        return s
    # Dạng chữ in hoa ngắn < 50 ký tự không kết thúc bằng dấu chấm:
    if len(s) < 50 and s.isupper() and not s.endswith("."):
        return s
    return None


def extract_text_from_pdf(file_bytes: bytes, doc_title: str) -> tuple[str, list[dict[str, Any]]]:
    """Bóc tách text từ file PDF theo trang, mục và đoạn."""
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    all_chunks: list[dict[str, Any]] = []
    full_text_parts: list[str] = []
    current_section = "Phần mở đầu"

    def append_page(page_idx: int, raw_text: str) -> None:
        nonlocal current_section
        page_text = _clean_text(raw_text)
        if not page_text:
            return
        full_text_parts.append(f"--- Trang {page_idx} ---\n{page_text}")

        # Tách các dòng để tìm tiêu đề mục (heading)
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        for line in lines:
            detected = _detect_heading(line)
            if detected:
                current_section = detected
                break

        # Tách trang thành các đoạn hợp lý (khoảng 300 - 800 ký tự)
        raw_paras = [p.strip() for p in page_text.split("\n\n") if len(p.strip()) > 20]
        if not raw_paras:
            raw_paras = [p.strip() for p in page_text.split("\n") if len(p.strip()) > 20]
        if not raw_paras:
            raw_paras = [page_text]

        for p_idx, para in enumerate(raw_paras, start=1):
            para_heading = _detect_heading(para.splitlines()[0]) if para.splitlines() else None
            section = para_heading or current_section
            location_detail = f"Mục: {section} · Trang {page_idx}, Đoạn {p_idx}"
            citation = f"[{doc_title}, Trang {page_idx}, Đoạn {p_idx}]"
            all_chunks.append({
                "page": page_idx,
                "paragraph": p_idx,
                "section_title": section,
                "location_detail": location_detail,
                "citation": citation,
                "content": para,
            })

    for page_idx, page in enumerate(reader.pages, start=1):
        append_page(page_idx, page.extract_text() or "")

    if not all_chunks:
        # OCR only when the PDF has no text layer. The caller already enforces
        # page, time, text and chunk budgets in a disposable child process.
        try:
            import pymupdf

            document = pymupdf.open(stream=file_bytes, filetype="pdf")
            try:
                for page_idx, page in enumerate(document, start=1):
                    text_page = page.get_textpage_ocr(
                        language="vie+eng",
                        dpi=150,
                        full=True,
                    )
                    append_page(page_idx, page.get_text(textpage=text_page))
            finally:
                document.close()
        except Exception as exc:
            logger.warning("pdf_ocr_failed error_type=%s", type(exc).__name__)

    full_text = "\n\n".join(full_text_parts)
    return full_text, all_chunks


def extract_text_from_docx(file_bytes: bytes, doc_title: str) -> tuple[str, list[dict[str, Any]]]:
    """Bóc tách text từ file Word (.docx) bằng chuẩn OpenXML."""
    all_chunks: list[dict[str, Any]] = []
    paragraphs: list[str] = []

    with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
        xml_content = z.read("word/document.xml")

    root = ET.fromstring(xml_content)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    for p in root.findall(".//w:p", ns):
        texts = [node.text for node in p.findall(".//w:t", ns) if node.text]
        p_text = _clean_text("".join(texts))
        if p_text:
            paragraphs.append(p_text)

    full_text = "\n\n".join(paragraphs)

    current_chunk: list[str] = []
    chunk_idx = 1
    current_section = "Nội dung chung"

    def flush() -> None:
        nonlocal current_chunk, chunk_idx
        if not current_chunk:
            return
        combined = "\n\n".join(current_chunk)
        location_detail = f"Mục: {current_section} · Đoạn {chunk_idx}"
        citation = f"[{doc_title}, {current_section}, Đoạn {chunk_idx}]"
        all_chunks.append({
            "page": None,
            "paragraph": chunk_idx,
            "section_title": current_section,
            "location_detail": location_detail,
            "citation": citation,
            "content": combined,
        })
        current_chunk = []
        chunk_idx += 1

    for p_idx, para in enumerate(paragraphs, start=1):
        detected = _detect_heading(para)
        if detected:
            # Never mix the tail of a public section with the first private
            # answer-key heading in the same chunk.
            flush()
            current_section = detected

        current_chunk.append(para)
        combined = "\n\n".join(current_chunk)
        if len(combined) >= 350 or p_idx == len(paragraphs):
            flush()

    return full_text, all_chunks


def extract_text_from_pptx(file_bytes: bytes, doc_title: str) -> tuple[str, list[dict[str, Any]]]:
    """Bóc tách text từ Slide bài giảng (.pptx) theo từng slide."""
    all_chunks: list[dict[str, Any]] = []
    slides_data: list[tuple[int, str]] = []

    with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
        slide_files = [f for f in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml", f)]

        def get_slide_num(name: str) -> int:
            m = re.search(r"slide(\d+)\.xml", name)
            return int(m.group(1)) if m else 0

        slide_files.sort(key=get_slide_num)
        ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}

        for s_file in slide_files:
            slide_num = get_slide_num(s_file)
            xml_content = z.read(s_file)
            root = ET.fromstring(xml_content)
            texts = [node.text for node in root.findall(".//a:t", ns) if node.text]
            slide_text = _clean_text(" ".join(texts))
            if slide_text:
                slides_data.append((slide_num, slide_text))

    full_text = "\n\n".join(f"--- Slide {num} ---\n{text}" for num, text in slides_data)

    for slide_num, text in slides_data:
        # Tiêu đề slide lấy từ phần đầu
        slide_lines = [line.strip() for line in text.split("  ") if line.strip()]
        slide_heading = slide_lines[0][:60] if slide_lines else f"Slide {slide_num}"
        section_title = f"Slide {slide_num}: {slide_heading}"
        location_detail = f"Slide {slide_num} · {slide_heading}"
        citation = f"[{doc_title}, Slide {slide_num}]"
        all_chunks.append({
            "page": slide_num,
            "paragraph": 1,
            "section_title": section_title,
            "location_detail": location_detail,
            "citation": citation,
            "content": f"Slide {slide_num} ({slide_heading}): {text}",
        })

    return full_text, all_chunks


def extract_text_from_plain(file_bytes: bytes, doc_title: str) -> tuple[str, list[dict[str, Any]]]:
    """Bóc tách text từ file .txt hoặc .md theo heading và đoạn."""
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1", errors="ignore")

    clean = _clean_text(text)
    paragraphs = [p.strip() for p in clean.split("\n\n") if len(p.strip()) > 20]
    if not paragraphs:
        paragraphs = [clean] if clean else []

    all_chunks: list[dict[str, Any]] = []
    current_section = "Nội dung chung"

    for idx, p in enumerate(paragraphs, start=1):
        detected = _detect_heading(p.splitlines()[0]) if p.splitlines() else None
        if detected:
            current_section = detected
        page_est = (idx // 3) + 1
        para_est = (idx % 3) + 1
        location_detail = f"Mục: {current_section} · Trang {page_est}, Đoạn {para_est}"
        citation = f"[{doc_title}, Trang {page_est}, Đoạn {para_est}]"
        all_chunks.append({
            "page": page_est,
            "paragraph": para_est,
            "section_title": current_section,
            "location_detail": location_detail,
            "citation": citation,
            "content": p,
        })

    return clean, all_chunks



def parse_material_content(
    file_bytes: bytes,
    file_name: str,
    doc_title: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Nhận diện định dạng file và bóc tách nội dung tương ứng."""
    ext = Path(file_name).suffix.lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_bytes, doc_title)
    elif ext in {".docx", ".doc"}:
        try:
            return extract_text_from_docx(file_bytes, doc_title)
        except Exception as exc:
            logger.warning("docx_extract_failed error_type=%s, fallback to plain", type(exc).__name__)
            return extract_text_from_plain(file_bytes, doc_title)
    elif ext in {".pptx", ".ppt"}:
        try:
            return extract_text_from_pptx(file_bytes, doc_title)
        except Exception as exc:
            logger.warning("pptx_extract_failed error_type=%s, fallback to plain", type(exc).__name__)
            return extract_text_from_plain(file_bytes, doc_title)
    else:
        # .txt, .md hoặc các file text khác
        return extract_text_from_plain(file_bytes, doc_title)


def index_material_in_qdrant(
    material: CourseMaterial,
    chunks: list[dict[str, Any]],
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> int:
    """
    Sinh embeddings bằng FastEmbed và upsert vào Qdrant Vector Store
    với đầy đủ metadata phân quyền và trích dẫn.
    """
    from qdrant_client.models import Distance, PointStruct, VectorParams

    if not chunks:
        return 0

    qdrant = _get_qdrant_client()

    # Đảm bảo collection tồn tại
    if not qdrant.collection_exists(collection_name):
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )

    # Sinh vector embeddings cho tất cả các đoạn
    embed_model = _get_embedding_model()
    texts_to_embed = [chunk["content"] for chunk in chunks]
    embeddings = list(embed_model.embed(texts_to_embed))

    points: list[PointStruct] = []
    for idx, (chunk, vec) in enumerate(zip(chunks, embeddings)):
        # Tạo point_id dạng UUID v5 cố định theo material.id và index
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{material.id}:{idx}"))

        points.append(
            PointStruct(
                id=point_id,
                vector=vec.tolist() if hasattr(vec, "tolist") else list(vec),
                payload={
                    "material_id": material.id,
                    "chunk_id": f"{material.id}_{idx}",
                    "document_title": material.title,
                    "module_name": material.module_name,
                    "course_id": str(material.course_id),
                    "institution_id": material.institution_id,
                    "access_scope": "course",
                    "file_name": material.file_name,
                    "file_type": material.file_type,
                    "section_title": chunk.get("section_title") or material.title,
                    "location_detail": chunk.get("location_detail") or f"Trang {chunk.get('page', 1)}",
                    "download_url": f"/api/v1/materials/{material.id}/download",
                    "preview_url": f"/api/v1/materials/{material.id}/preview",
                    "page": chunk.get("page", 1),
                    "paragraph": chunk.get("paragraph", idx + 1),
                    "citation": chunk.get("citation", f"[{material.title}]"),
                    "content": chunk["content"],
                },
            )
        )

    # Upsert vào Qdrant
    qdrant.upsert(collection_name=collection_name, points=points)
    clear_retrieval_cache()
    logger.info(
        "qdrant_material_indexed material_id=%s course_id=%s chunks=%d",
        material.id,
        material.course_id,
        len(points),
    )
    return len(points)


def delete_material_from_qdrant(
    material_id: str,
    institution_id: str,
    course_id: int,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> None:
    """Xóa tất cả các points thuộc tài liệu này khỏi Qdrant."""
    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

    qdrant = _get_qdrant_client()
    if not qdrant.collection_exists(collection_name):
        return

    qdrant.delete(
        collection_name=collection_name,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(key="material_id", match=MatchValue(value=material_id)),
                    FieldCondition(key="institution_id", match=MatchValue(value=institution_id)),
                    FieldCondition(key="course_id", match=MatchValue(value=str(course_id))),
                ]
            )
        ),
        wait=True,
    )
    clear_retrieval_cache()
    logger.info("qdrant_material_deleted material_id=%s", material_id)
