import asyncio
import multiprocessing
import time
from unittest.mock import Mock

import pytest

from src.config import Settings
from src.services import document_extraction as extraction


@pytest.mark.parametrize("chunks,max_chars,max_chunks,reason", [
    ([{"content": "a" * 2000}], 1000, 10, "text_limit"),
    ([{"content": "a" * 3601}], 5000, 2, "chunk_limit"),
    ([], 1000, 2, "empty_text"),
])
def test_extraction_budgets_before_index(monkeypatch, chunks, max_chars, max_chunks, reason):
    monkeypatch.setattr("src.services.lms_files.validate_document", Mock())
    monkeypatch.setattr("src.services.material_service.parse_material_content", Mock(return_value=("", chunks)))
    with pytest.raises(ValueError, match=reason):
        extraction.extract_document(b"pdf", "chapter.pdf", "Chapter 3", 1000, max_chunks, max_chars)


def _slow_child(pipe, args):
    time.sleep(30)


@pytest.mark.asyncio
async def test_timeout_terminates_process_instead_of_leaking_background_thread(monkeypatch):
    before = {child.pid for child in multiprocessing.active_children()}
    monkeypatch.setattr(extraction, "_extract_child", _slow_child)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        await extraction.bounded_extract(b"pdf", "chapter.pdf", "Chapter 3", Settings(_env_file=None, course_file_processing_seconds=1))
    assert time.monotonic() - started < 10
    assert {child.pid for child in multiprocessing.active_children()} <= before


@pytest.mark.asyncio
async def test_cancellation_also_terminates_child(monkeypatch):
    before = {child.pid for child in multiprocessing.active_children()}
    monkeypatch.setattr(extraction, "_extract_child", _slow_child)
    job = asyncio.create_task(extraction.bounded_extract(b"pdf", "chapter.pdf", "Chapter 3", Settings(_env_file=None)))
    await asyncio.sleep(0.2)
    job.cancel()
    with pytest.raises(asyncio.CancelledError):
        await job
    assert {child.pid for child in multiprocessing.active_children()} <= before


def _slow_index(pipe, job, settings):
    time.sleep(30)


def test_embedding_deadline_also_terminates_child(monkeypatch):
    from src.services import file_indexing

    before = {child.pid for child in multiprocessing.active_children()}
    monkeypatch.setattr(file_indexing, "_index_child", _slow_index)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        file_indexing.bounded_index({}, Settings(_env_file=None, course_file_processing_seconds=1))
    assert time.monotonic() - started < 10
    assert {child.pid for child in multiprocessing.active_children()} <= before
