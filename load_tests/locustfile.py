"""Production-like PaceWise load profile; supports a 1,000-user acceptance run."""

from __future__ import annotations

import os
import random

from locust import HttpUser, between, task


class PaceWiseUser(HttpUser):
    wait_time = between(1, 4)

    def on_start(self) -> None:
        response = self.client.post(
            "/api/v1/auth/lms-login",
            json={
                "email": os.getenv("LOAD_TEST_EMAIL", "student@canvas.local"),
                "password": os.getenv("LOAD_TEST_PASSWORD", "demo123"),
                "course_id": int(os.getenv("LOAD_TEST_COURSE_ID", "1")),
            },
            name="POST /auth/lms-login",
        )
        if response.ok:
            self.csrf = self.client.cookies.get("pacewise_csrf", "")
        else:
            self.csrf = ""

    @property
    def headers(self) -> dict[str, str]:
        return {"X-CSRF-Token": self.csrf}

    @task(5)
    def sync_lms(self) -> None:
        self.client.get("/api/v1/lms/sync", name="GET /lms/sync")

    @task(3)
    def tracking(self) -> None:
        self.client.post(
            "/api/v1/chat",
            headers=self.headers,
            json={"message": "Kiểm tra tiến độ và deadline", "workflow": "tracking", "context": {}},
            name="POST /chat tracking",
        )

    @task(1)
    def grounded_qa(self) -> None:
        question = random.choice(("Giải thích nội dung bài học", "Tóm tắt khái niệm chính"))
        self.client.post(
            "/api/v1/chat",
            headers=self.headers,
            json={"message": question, "workflow": "qa", "context": {}},
            name="POST /chat qa",
        )
