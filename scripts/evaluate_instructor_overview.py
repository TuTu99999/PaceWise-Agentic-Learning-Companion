"""Local encrypted HTTP smoke; emits only aggregate counts and status codes."""

import json
from time import perf_counter

from private_client import PrivateClient


def check(role):
    email = "teacher@canvas.local" if role == "instructor" else "student@canvas.local"
    with PrivateClient(base_url="http://localhost:5173", timeout=30) as client:
        login = client.post("/api/v1/auth/lms-login", json={"email": email, "password": "demo123"})
        assert login.status_code == 200
        csrf = {"X-CSRF-Token": client.cookies["pacewise_csrf"]}
        try:
            started = perf_counter()
            response = client.get("/api/v1/instructor/overview")
            result = {"role": role, "status": response.status_code, "duration_ms": round((perf_counter() - started) * 1000)}
            if role == "student":
                assert response.status_code == 403
                return result
            assert response.status_code == 200
            payload = response.json()
            minimum = payload["privacy"]["minimumGroupSize"]
            assert minimum >= 5
            assert payload["lmsSummary"] is None
            assert not any(item["id"].startswith("EV-") for item in payload["reviewQueue"])
            assert all("missingMinutes" not in item for stats in payload["groupStats"].values()
                       for item in stats["assignmentRisks"])
            assert all(item["n"] >= minimum for stats in payload["groupStats"].values() for item in stats["topics"])
            cycle_statuses = []
            for stats in payload["groupStats"].values():
                comparison = stats["adoptionComparison"]
                assert comparison["method"] == "paired_observational_first_plan_confirmation_v2"
                assert comparison["adoptionEvent"] == "PLAN_CONFIRMED"
                assert comparison["windowDays"] == 14
                metrics = stats["learningCycle"]
                assert metrics["version"] == "plan-measurement-v1"
                assert metrics["causalClaim"] is False
                assert metrics["progressBeforePaceWise"] is None
                assert "student_ids" not in metrics and "evidence" not in metrics
                for name in ("originalPlan", "currentPlan", "learningEvidence"):
                    section = metrics[name]
                    if section["status"] == "available":
                        assert section["n"] >= minimum
                    else:
                        assert section["rate"] is None and section["total"] is None
                cycle_statuses.append({name: metrics[name]["status"]
                                       for name in ("originalPlan", "currentPlan", "learningEvidence")})
            result.update({"student_count": sum(group["n"] for group in payload["classGroups"]),
                           "small_cohort_suppressed": not bool(payload["groupStats"]),
                           "topic_privacy_check": "passed", "no_points_based_duration": True,
                           "no_grade_as_uncertain_ai_review": True,
                           "learning_kpi_contract": "passed" if cycle_statuses else "cohort_suppressed",
                           "learning_kpi_statuses": cycle_statuses})
            return result
        finally:
            assert client.post("/api/v1/auth/logout", headers=csrf).status_code == 200


if __name__ == "__main__":
    print(json.dumps([check("instructor"), check("student")], indent=2))
