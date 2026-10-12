"""Small auth/pool smoke, not a 1,000-student capacity certification."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from private_client import PrivateClient


def one(index):
    base = "http://localhost:5173"
    email = "student@canvas.local" if index % 2 else "teacher@canvas.local"
    with PrivateClient(base_url=base, timeout=20, headers={"Origin": base}) as client:
        start = time.perf_counter()
        result = client.post("/api/v1/auth/login", json={"email": email, "password": "demo123"})
        assert result.status_code == 200, f"Concurrent login status {result.status_code}"
        login_ms = round((time.perf_counter() - start) * 1000)
        client.headers["X-CSRF-Token"] = client.cookies["pacewise_csrf"]
        assert client.get("/api/v1/auth/me").status_code == 200
        start = time.perf_counter()
        assert client.post("/api/v1/auth/logout").status_code == 200
        return {"login_ms": login_ms, "logout_ms": round((time.perf_counter() - start) * 1000)}


def main():
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(one, range(20)))
    report = {"passed": True, "simultaneous_auth_clients": 20, "all_logout_ok": True,
              "max_login_ms": max(item["login_ms"] for item in results),
              "max_logout_ms": max(item["logout_ms"] for item in results),
              "not_a_1000_student_load_test": True}
    path = Path(__file__).resolve().parents[1] / "evals/reports/standalone-auth-pool-2026-10-10.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
