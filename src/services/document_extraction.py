"""Bounded extraction in a disposable process, not an uncancellable thread."""

import asyncio
import multiprocessing


class DocumentLimitError(ValueError):
    pass


def extract_document(data, filename, title, max_pages, max_chunks, max_chars):
    from src.services.lms_files import validate_document
    from src.services.material_service import parse_material_content

    validate_document(data, filename, max_pages)
    full_text, chunks = parse_material_content(data, filename, title)
    if len(full_text) > max_chars or sum(len(str(c.get("content") or "")) for c in chunks) > max_chars:
        raise DocumentLimitError("text_limit")
    # The indexer splits paragraphs into 1800-character citation chunks.
    count = sum((len(str(c.get("content") or "")) + 1799) // 1800 for c in chunks)
    if count > max_chunks:
        raise DocumentLimitError("chunk_limit")
    if not chunks or not count:
        raise ValueError("empty_text")
    return chunks


def _extract_child(pipe, args):
    try:
        pipe.send((True, extract_document(*args)))
    except Exception as exc:
        # Never send content, paths or arbitrary exception text to the parent/UI.
        reason = str(exc) if isinstance(exc, DocumentLimitError) else "invalid_or_unreadable"
        pipe.send((False, reason))
    finally:
        pipe.close()


async def bounded_extract(data, filename, title, settings):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_extract_child, args=(child, (
        data, filename, title, settings.course_pdf_max_pages if settings.course_source_mode == "standalone" else 500,
        settings.course_file_max_chunks, settings.course_file_max_text_chars,
    )), daemon=True)
    try:
        process.start()
        child.close()
        ready = await asyncio.to_thread(parent.poll, settings.course_file_processing_seconds)
        if not ready:
            raise TimeoutError("extraction_timeout")
        try:
            ok, value = await asyncio.to_thread(parent.recv)
        except EOFError as exc:
            raise ValueError("extractor_stopped") from exc
        if not ok:
            raise DocumentLimitError(value) if value in {"text_limit", "chunk_limit"} else ValueError(value)
        return value
    finally:
        if process.pid:
            if process.is_alive():
                process.terminate()
            await asyncio.to_thread(process.join, 5)
            if process.is_alive():
                process.kill()
                await asyncio.to_thread(process.join, 5)
            process.close()
        parent.close()
        child.close()
