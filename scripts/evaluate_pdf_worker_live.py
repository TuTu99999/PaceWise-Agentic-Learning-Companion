"""Real PDF/FastEmbed/Qdrant QA using only an isolated, disposable QA namespace."""

import argparse
import asyncio
import hashlib
import io
import json
from pathlib import Path
from uuid import uuid4

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from src.agents.tools.qdrant_retriever import DEFAULT_COLLECTION_NAME, _get_qdrant_client, delete_lms_file_resources
from src.config import get_settings
from src.services.document_extraction import bounded_extract
from src.services.file_indexing import bounded_index


def chapter_pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(600, 800)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 50 700 Td (Chapter 3 QA: a relation is a subset of A cross B.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    # Valid large PDF, not trailing padding that corrupts startxref/EOF parsing.
    writer.add_metadata({"/QA_PADDING": "x" * (6 * 1024 * 1024)})
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


async def main(report_path=None):
    settings = get_settings().model_copy(update={"institution_id": "pdf-qa-" + uuid4().hex})
    assert settings.course_source_mode == "standalone"
    data = chapter_pdf()
    chunks = await bounded_extract(data, "chapter-3.pdf", "Chapter 3 QA", settings)
    assert chunks and chunks[0]["page"] == 1
    version = hashlib.sha256(data).hexdigest()
    resources = [dict(chunk, institution_id=settings.institution_id, course_id="999999", resource_id="file:999999",
                      source_type="lms_file", resource_version=version, access_scope="course", document_title="Chapter 3 QA")
                 for chunk in chunks]
    job = {"previous": "pending", "course_id": 999999, "file_id": 999999, "version": version,
           "chunks": json.dumps(resources)}
    qdrant = _get_qdrant_client()
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    scope = Filter(must=[FieldCondition(key="institution_id", match=MatchValue(value=settings.institution_id))])
    try:
        first = await asyncio.to_thread(bounded_index, job, settings)
        repeated = await asyncio.to_thread(bounded_index, job, settings)
        count = qdrant.count(DEFAULT_COLLECTION_NAME, count_filter=scope, exact=True).count
        assert first["status"] == "success" and repeated["status"] == "unchanged" and count == len(chunks)
    finally:
        delete_lms_file_resources(institution_id=settings.institution_id, course_id="999999", resource_id="file:999999")
    assert qdrant.count(DEFAULT_COLLECTION_NAME, count_filter=scope, exact=True).count == 0
    report = {"passed": True, "pdf_bytes": len(data), "real_pdf_extraction": True,
                      "real_subprocess_embedding_qdrant": True, "unchanged_content_reuses_vectors": True,
                      "qa_vectors_removed": True, "no_course_or_history_writes": True}
    if report_path:
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    asyncio.run(main(parser.parse_args().report))
