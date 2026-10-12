import asyncio
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import HTTPException

from src.config import Settings

# Keep aggregate backend traffic below the lightweight simulator's database
# connection budget. This limiter is shared by every LMSClient in one process.
_LMS_REQUEST_LIMITER = asyncio.Semaphore(8)


class LMSClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.base_url = settings.lms_base_url.rstrip("/")
        self.timeout = httpx.Timeout(12.0, connect=4.0)
        self._client = client

    def _owned_client(self, **kwargs) -> httpx.AsyncClient:
        if self.settings.course_source_mode == "standalone":
            from src.course_source.gateway import internal_app

            return httpx.AsyncClient(transport=httpx.ASGITransport(app=internal_app()),
                                     base_url="http://pacewise-course-source", timeout=self.timeout, **kwargs)
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout, **kwargs)

    def _service_headers(self) -> dict[str, str]:
        if self.settings.course_source_mode == "standalone":
            return {}
        if not self.settings.pacewise_api_key.strip():
            raise HTTPException(status_code=503, detail="PACEWISE_API_KEY is not configured")
        return {"X-PaceWise-Key": self.settings.pacewise_api_key}

    async def _request(self, method: str, path: str, *, allow_domain_errors: bool = False, **kwargs) -> httpx.Response:
        async with _LMS_REQUEST_LIMITER:
            try:
                if self._client:
                    response = await self._client.request(method, path, timeout=self.timeout, **kwargs)
                else:
                    async with self._owned_client() as client:
                        response = await client.request(method, path, **kwargs)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                raise HTTPException(status_code=503, detail="LMS simulator is unavailable") from exc
            except httpx.TimeoutException as exc:
                raise HTTPException(status_code=504, detail="LMS simulator timed out") from exc
        if response.status_code in {401, 403}:
            detail = response.json().get("detail", "LMS authorization failed") if response.content else "LMS authorization failed"
            raise HTTPException(status_code=response.status_code, detail=detail)
        if response.is_error:
            if allow_domain_errors and response.status_code in {404, 409, 422}:
                detail = response.json().get("detail")
                raise HTTPException(response.status_code, detail if isinstance(detail, str) else "Dữ liệu không hợp lệ. Kiểm tra các trường và tổng điểm/trọng số.")
            raise HTTPException(status_code=502, detail=f"LMS request failed ({response.status_code})")
        return response

    async def verify_launch(self, token: str) -> dict:
        if self.settings.course_source_mode == "standalone":
            raise HTTPException(410, "PaceWise chạy độc lập. Hãy đăng nhập trực tiếp.")
        response = await self._request(
            "POST",
            "/api/pacewise/v1/launch/verify",
            headers=self._service_headers(),
            json={"token": token},
        )
        return response.json()

    async def service_get(self, path: str, params: dict | None = None):
        response = await self._request("GET", path, headers=self._service_headers(), params=params)
        return response.json()

    async def service_post(self, path: str, payload: dict):
        response = await self._request("POST", path, headers=self._service_headers(), json=payload)
        return response.json()

    async def teacher_request(self, method: str, path: str, *, user_id: int, payload: dict | None = None):
        response = await self._request(method, path, headers=self._service_headers(), params={"user_id": user_id},
                                       json=payload, allow_domain_errors=True)
        return response.json()

    async def service_get_many(self, requests: list[tuple[str, dict | None]]) -> list[Any]:
        """One bounded HTTP pool per snapshot, never shared cookies between accounts."""
        async def collect(client: LMSClient) -> list[Any]:
            # Drain siblings on an upstream failure before closing their transport.
            results = await asyncio.gather(
                *(client.service_get(path, params) for path, params in requests), return_exceptions=True
            )
            for result in results:
                if isinstance(result, BaseException):
                    raise result
            return results

        if self._client is not None:
            return await collect(self)
        async with self._owned_client(limits=httpx.Limits(max_connections=8, max_keepalive_connections=8)) as pooled:
            return await collect(LMSClient(self.settings, pooled))

    async def download_course_file(self, course_id: int, file_id: int, *, user_id: int | None = None) -> bytes:
        """Bounded, authenticated download from a fixed LMS endpoint, not an arbitrary URL."""
        path = f"/api/pacewise/v1/courses/{int(course_id)}/files/{int(file_id)}/download"
        params = {"user_id": user_id} if user_id is not None else None
        client = self._client or self._owned_client()
        try:
            async with _LMS_REQUEST_LIMITER:
                async with client.stream("GET", path, headers=self._service_headers(), params=params, timeout=self.timeout, follow_redirects=False) as response:
                    if response.status_code in {401, 403, 404}:
                        raise HTTPException(response.status_code, "LMS file access denied or file no longer exists")
                    if response.status_code != 200:
                        raise HTTPException(502, "LMS file download failed")
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        limit_mb = self.settings.course_pdf_max_mb if self.settings.course_source_mode == "standalone" else 20
                        if size > limit_mb * 1024 * 1024:
                            raise HTTPException(413, "File exceeds configured size limit")
                        chunks.append(chunk)
                    return b"".join(chunks)
        except httpx.HTTPError as exc:
            raise HTTPException(503, "LMS file download unavailable") from exc
        finally:
            if self._client is None:
                await client.aclose()

    async def login_and_create_launch(self, email: str, password: str, course_id: int | None = None) -> dict:
        if self.settings.course_source_mode == "standalone":
            from src.course_source.auth import login

            async with _LMS_REQUEST_LIMITER:
                return await asyncio.to_thread(login, email, password, course_id)
        login = await self._request("POST", "/api/session", headers=self._service_headers(),
                                    json={"email": email, "password": password})
        payload = login.json()
        access_token = payload["access_token"]
        csrf_token = payload["csrf_token"]
        headers = {"Authorization": f"Bearer {access_token}", "X-CSRF-Token": csrf_token}
        try:
            courses_response = await self._request("GET", "/api/v1/courses", headers=headers)
            courses = courses_response.json()
            if not courses:
                raise HTTPException(status_code=403, detail="This LMS account has no enrolled courses")
            selected_id = course_id if course_id is not None else int(courses[0]["id"])
            if selected_id not in {int(course["id"]) for course in courses}:
                raise HTTPException(status_code=403, detail="Course enrollment required")
            launch = await self._request(
                "POST",
                f"/api/pacewise/launch/{selected_id}",
                headers=headers,
            )
            parsed_launch = urlparse(launch.json()["launch_url"])
            launch_query = parsed_launch.query
            if not launch_query and "?" in parsed_launch.fragment:
                launch_query = parsed_launch.fragment.split("?", 1)[1]
            token = parse_qs(launch_query).get("token", [""])[0]
            if not token:
                raise HTTPException(status_code=502, detail="LMS returned an invalid launch URL")
            return await self.verify_launch(token)
        finally:
            try:
                await self._request("DELETE", "/api/session", headers=headers)
            except HTTPException:
                pass
