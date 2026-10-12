"""Read-only domain smoke with preserved demo accounts and encrypted HTTP.

Only auth sessions/login/logout are written. No learner plan, timer or teacher
data is changed. Output is aggregate statuses/counts, never identities/tokens.
"""

import json
import subprocess
import time
from pathlib import Path

from private_client import PrivateClient


def checked(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    if response.status_code != 200:
        raise RuntimeError(f"{path.split('?')[0]} returned {response.status_code}")
    return response.json()


def main():
    stopped = subprocess.check_output(["docker", "ps", "-a", "--format", "{{.Names}}|{{.State}}"], text=True)
    for name in ("pacewise-lms-lms-simulator-1", "pacewise-lms-lms-postgres-1"):
        assert name + "|exited" in stopped, "Old source must be stopped during smoke"
    reports = []
    base = "http://localhost:5173"
    for role, email in [("student", "student@canvas.local"), ("instructor", "teacher@canvas.local")]:
        with PrivateClient(base_url=base, headers={"Origin": base}, timeout=45) as client:
            start = time.perf_counter()
            auth = checked(client, "POST", "/api/v1/auth/login", json={"email": email, "password": "demo123"})
            assert auth["user"]["role"] == role
            client.headers["X-CSRF-Token"] = client.cookies["pacewise_csrf"]
            login_ms = round((time.perf_counter() - start) * 1000)
            checked(client, "GET", "/api/v1/auth/me")
            workspace = checked(client, "GET", "/api/v1/workspace")
            synced = checked(client, "GET", "/api/v1/lms/sync")
            course_ids = {str(course["id"]) for course in synced["courses"]}
            record = {"role": role, "login": "passed", "login_ms": login_ms,
                      "courses": len(course_ids), "tasks": len(synced["tasks"]), "workspace": "passed"}
            if role == "instructor":
                courses = checked(client, "GET", "/api/v1/instructor/manage/courses")
                assert courses
                checked(client, "GET", "/api/v1/instructor/manage/profile")
                for course in courses:
                    if course["archived"]:
                        continue
                    snapshot = checked(client, "GET", f"/api/v1/instructor/manage/courses/{course['id']}")
                    assert all(key in snapshot for key in ("tasks", "lessons", "resources", "weights"))
                checked(client, "GET", "/api/v1/instructor/overview")
                record["authoring_reads_and_overview"] = "passed"
            else:
                denied = client.get("/api/v1/instructor/manage/courses")
                assert denied.status_code == 403
                blocks = ((workspace.get("state") or {}).get("plan") or {}).get("blocks") or []
                prepared, file_checked = 0, False
                for block in sorted(blocks, key=lambda item: (item.get("date", ""), item.get("start", "")), reverse=True):
                    course_id = str(block.get("taskId", "")).split(":", 1)[0]
                    if course_id not in course_ids or block.get("status") in {"tentative", "history"}:
                        continue
                    result = client.post("/api/v1/study-sessions/prepare", json={"courseId": int(course_id), "blockId": block["id"]})
                    if result.status_code == 409:
                        continue  # Obsolete blocks stay unchanged; no demo reseeding.
                    assert result.status_code == 200, f"Do prepare status {result.status_code}"
                    data = result.json()
                    assert data["block_id"] == block["id"] and len(data["recommended_resources"]) <= 3
                    prepared += 1
                    for resource in data["recommended_resources"]:
                        url = resource.get("url") or ""
                        if not file_checked and url.startswith("/api/v1/private/files/"):
                            pdf = client.get(url)
                            assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
                            file_checked = True
                    if prepared >= 3 and file_checked:
                        break
                record.update({"teacher_role_denied": True, "confirmed_do_prepared": prepared, "preserved_pdf_download": file_checked})
                assert prepared > 0, "No valid preserved confirmed block; do not fabricate a demo success"
            session_cookie = client.cookies.get("pacewise_session")
            start = time.perf_counter()
            result = checked(client, "POST", "/api/v1/auth/logout")
            assert result["ok"]
            record["logout_ms"] = round((time.perf_counter() - start) * 1000)
            assert client.get("/api/v1/auth/me").status_code == 401
            assert client.get("/api/v1/auth/me", headers={"Cookie": "pacewise_session=" + session_cookie}).status_code == 401
            record["logout_cookie_replay_denied"] = True
            reports.append(record)
    report = {"target": "real_docker_with_old_source_api_and_database_stopped", "passed": True, "results": reports}
    path = Path(__file__).resolve().parents[1] / "evals/reports/standalone-live-2026-10-10.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
