"""Hard per-file index deadline, including embedding/model loading."""

import json
import multiprocessing


def index_file_job(job, settings):
    from src.agents.tools.qdrant_retriever import delete_lms_file_resources, ingest_course_resources

    deleting = job["previous"] == "delete_pending"
    result = {"status": "deleted", "total_chunks": 0}
    if not deleting:
        result = ingest_course_resources(json.loads(job["chunks"]))
    delete_lms_file_resources(
        institution_id=settings.institution_id, course_id=str(job["course_id"]),
        resource_id=f"file:{job['file_id']}", keep_version=None if deleting else job["version"],
    )
    return result


def _index_child(pipe, job, settings):
    try:
        pipe.send({"ok": True, "result": index_file_job(job, settings)})
    except Exception:
        pipe.send({"ok": False})
    finally:
        pipe.close()


def bounded_index(job, settings):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_index_child, args=(child, job, settings), daemon=True)
    try:
        process.start()
        child.close()
        if not parent.poll(settings.course_file_processing_seconds):
            raise TimeoutError("index_timeout")
        outcome = parent.recv()
        if not outcome["ok"]:
            raise RuntimeError("index_unavailable")
        return outcome["result"]
    finally:
        if process.pid:
            if process.is_alive():
                process.terminate()
            process.join(5)
            if process.is_alive():
                process.kill()
                process.join(5)
            process.close()
        parent.close()
        child.close()
