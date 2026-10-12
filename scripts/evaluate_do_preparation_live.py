"""Read-only Docker smoke: preparation + PDF, no timer, plan edit or LLM call.

Uses public simulator demo credentials only. Outputs counts/statuses, never
learner identity, response bodies, session cookies or opaque download tokens.
"""
import json
import os
import time

from private_client import PrivateClient


def main():
    base = os.environ.get("DO_SMOKE_BASE_URL", "http://localhost:5173")
    with PrivateClient(base_url=base, timeout=45, headers={"Origin": base}) as client:
        login = client.post("/api/v1/auth/lms-login", json={
            "email": "student@canvas.local", "password": "demo123", "course_id": 1})
        assert login.status_code == 200, f"Login status {login.status_code}"
        client.headers["X-CSRF-Token"] = client.cookies.get("pacewise_csrf")
        workspace = client.get("/api/v1/workspace")
        assert workspace.status_code == 200
        blocks = (workspace.json().get("state", {}).get("plan") or {}).get("blocks") or []
        assert blocks, "No confirmed demo plan; create/confirm a plan in PaceWise first"
        synced = client.get("/api/v1/lms/sync")
        assert synced.status_code == 200
        courses = {str(course["id"]): course["code"] for course in synced.json()["courses"]}
        slide_course = next((identifier for identifier, code in courses.items() if code == "DS201"), "")
        reports, downloaded = [], False
        # Later blocks are more likely still before current LMS deadlines.
        for block in sorted(blocks, key=lambda row: (str(row.get("taskId", "")).partition(":")[0] == slide_course,
                          row.get("date", ""), row.get("start", "")), reverse=True):
            if block.get("status") in {"tentative", "history"}:
                continue
            course = str(block.get("taskId", "")).partition(":")[0]
            if not course.isdigit():
                continue
            payload = {"courseId": int(course), "blockId": block["id"]}
            begin = time.perf_counter()
            response = client.post("/api/v1/study-sessions/prepare", json=payload)
            if response.status_code == 409:
                continue  # An obsolete block is not a reason to mutate a learner's plan.
            assert response.status_code == 200, f"Prepare status {response.status_code}"
            data = response.json()
            again = client.post("/api/v1/study-sessions/prepare", json=payload)
            assert again.status_code == 200
            assert again.json()["resource_version"] == data["resource_version"]
            assert len(data["recommended_resources"]) <= 3
            assert data["objective"] == (block.get("milestoneTitle") or "Ca tự học cho nhiệm vụ này")
            reports.append({"course_code": courses.get(course), "mapped": data["scope"]["status"] == "mapped",
                "material_kinds": [resource["kind"] for resource in data["recommended_resources"]],
                "materials": len(data["recommended_resources"]), "session_minutes": data["planned_minutes"],
                "elapsed_two_requests_ms": round((time.perf_counter() - begin) * 1000), "stable_version": True})
            for resource in data["recommended_resources"]:
                url = resource.get("url") or ""
                if not downloaded and "/api/v1/private/files/" in url:
                    file = client.get(url)
                    assert file.status_code == 200, f"File status {file.status_code}"
                    assert file.content.startswith(b"%PDF-"), "Slide is not a valid PDF"
                    downloaded = True
            if downloaded or len(reports) >= 4:
                break
        assert reports, "No still-valid server-confirmed blocks available for smoke test"
        invalid = client.post("/api/v1/study-sessions/prepare", json={"courseId": 1, "blockId": "unconfirmed-smoke"})
        assert invalid.status_code == 409
        logout = client.post("/api/v1/auth/logout")
        assert logout.status_code == 200
        assert client.get("/api/v1/workspace").status_code == 401
        print(json.dumps({"mode": "live Docker / encrypted API", "preparations": reports,
            "pdf_download_verified": downloaded, "unconfirmed_rejected": True, "logout_verified": True}))


if __name__ == "__main__":
    main()
