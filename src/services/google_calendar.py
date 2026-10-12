"""Small Google OAuth/Calendar REST client with no Google SDK runtime cost."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import random
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

from src.config import Settings
from src.services.calendar_quota import cooldown, google_admission

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"

# Google may return canonical identity scopes rather than the requested aliases.
# Calendar permissions remain exact: identity aliases never imply Calendar access.
_IDENTITY_SCOPE_ALIASES = {
    "email": "https://www.googleapis.com/auth/userinfo.email",
    "profile": "https://www.googleapis.com/auth/userinfo.profile",
}


def canonical_google_scopes(scopes: str) -> set[str]:
    """Normalize known Google identity aliases without broadening permissions."""
    return {_IDENTITY_SCOPE_ALIASES.get(scope, scope) for scope in scopes.split()}


class GoogleCalendarError(RuntimeError):
    """A safe, user-displayable integration error."""


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    refresh_token: str | None
    scope: str


def new_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def hash_oauth_state(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def new_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


class TokenCipher:
    def __init__(self, settings: Settings):
        key = settings.google_token_encryption_key.strip()
        if not key:
            raise GoogleCalendarError("Google Calendar token encryption is not configured")
        try:
            self._fernet = Fernet(key.encode())
        except (TypeError, ValueError) as exc:
            raise GoogleCalendarError("GOOGLE_TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise GoogleCalendarError("Stored Google Calendar credentials cannot be decrypted") from exc


class GoogleCalendarClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None, *, user_id: int = 0):
        self.settings = settings
        self._client = client
        self.user_id = user_id

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.google_client_id.strip()
            and self.settings.google_client_secret.strip()
            and self.settings.google_token_encryption_key.strip()
        )

    def authorization_url(self, state: str, code_challenge: str) -> str:
        if not self.configured:
            raise GoogleCalendarError("Google Calendar is not configured")
        params = {
            "client_id": self.settings.google_client_id,
            "redirect_uri": self.settings.google_redirect_uri,
            "response_type": "code",
            "scope": self.settings.google_calendar_scopes,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"

    async def _post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("POST", url, **kwargs)

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("GET", url, **kwargs)

    async def _request(self, method, url, *, allow_conflict=False, **kwargs):
        for attempt in range(2):
            try:
                async with google_admission(self.settings, self.user_id), asyncio.timeout(20):
                    if self._client:
                        response = await self._client.request(method, url, timeout=15, **kwargs)
                    else:
                        async with httpx.AsyncClient() as client:
                            response = await client.request(method, url, timeout=15, **kwargs)
            except (httpx.HTTPError, TimeoutError) as exc:
                # Do not automatically repeat an uncertain write; explicit retry uses stable event IDs.
                raise GoogleCalendarError("Cannot reach Google Calendar") from exc
            if response.status_code == 409 and allow_conflict:
                return response
            reasons = set()
            if response.status_code == 403:
                try:
                    reasons = {item.get("reason") for item in response.json().get("error", {}).get("errors", [])}
                except (ValueError, AttributeError, TypeError):
                    pass
            limited = response.status_code == 429 or bool(
                reasons & {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded"}
            )
            if limited:
                try:
                    delay = min(60, max(1, float(response.headers.get("Retry-After", "1"))))
                except ValueError:
                    delay = 1
                await asyncio.to_thread(cooldown, delay)
                if attempt == 0 and delay <= 5:
                    await asyncio.sleep(delay + random.uniform(0.01, 0.5))
                    continue
                from src.services.calendar_quota import CalendarQuotaExceeded

                raise CalendarQuotaExceeded(delay, reason="provider_limit")
            if response.status_code >= 400:
                raise GoogleCalendarError(f"Google Calendar rejected the request ({response.status_code})")
            return response
        raise GoogleCalendarError("Google Calendar unavailable")

    async def exchange_code(self, code: str, code_verifier: str) -> OAuthTokens:
        response = await self._post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": self.settings.google_client_id,
                "client_secret": self.settings.google_client_secret,
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": self.settings.google_redirect_uri,
            },
        )
        payload = response.json()
        if not payload.get("access_token"):
            raise GoogleCalendarError("Google did not return an access token")
        return OAuthTokens(
            access_token=str(payload["access_token"]),
            refresh_token=str(payload["refresh_token"]) if payload.get("refresh_token") else None,
            scope=str(payload.get("scope") or ""),
        )

    async def access_token(self, refresh_token: str) -> str:
        from src.db import SessionLocal
        from src.services.calendar_cache import cache_key, read_cache, store_cache

        cipher = TokenCipher(self.settings)
        key = cache_key(self.user_id, refresh_token, "access-token")
        with SessionLocal() as db:
            cached = read_cache(db, key, cipher)
        if cached:
            return cached["token"]
        response = await self._post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": self.settings.google_client_id,
                "client_secret": self.settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        token = response.json().get("access_token")
        if not token:
            raise GoogleCalendarError("Google did not refresh the access token")
        try:
            ttl = min(3000, max(0, int(response.json().get("expires_in", 0)) - 60))
        except (ValueError, TypeError):
            ttl = 0
        if ttl:
            with SessionLocal() as db:
                store_cache(db, key, self.user_id, {"token": str(token)}, cipher, ttl)
                db.commit()
        return str(token)

    async def account_email(self, access_token: str) -> str | None:
        response = await self._get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        email = response.json().get("email")
        return str(email) if email else None

    async def freebusy(
        self,
        access_token: str,
        time_min: str,
        time_max: str,
        time_zone: str,
        calendar_id: str = "primary",
    ) -> list[dict[str, str]]:
        response = await self._post(
            f"{GOOGLE_CALENDAR_API}/freeBusy",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "timeMin": time_min,
                "timeMax": time_max,
                "timeZone": time_zone,
                "items": [{"id": calendar_id}],
            },
        )
        calendars = response.json().get("calendars", {})
        calendar = calendars.get(calendar_id)
        if calendar is None and len(calendars) == 1:
            calendar = next(iter(calendars.values()))
        calendar = calendar or {}
        if calendar.get("errors"):
            raise GoogleCalendarError("Google could not read calendar availability")
        return [
            {"start": str(item["start"]), "end": str(item["end"])}
            for item in calendar.get("busy", [])
            if item.get("start") and item.get("end")
        ]

    async def create_event(
        self,
        access_token: str,
        summary: str,
        start: str,
        end: str,
        time_zone: str,
        block_id: str,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        event_id = hmac.new(
            self.settings.pacewise_session_secret.encode(),
            f"{self.user_id}:{calendar_id}:{block_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        response = await self._post(
            f"{GOOGLE_CALENDAR_API}/calendars/{quote(calendar_id, safe='')}/events",
            allow_conflict=True,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"sendUpdates": "none"},
            json={
                "id": event_id,
                "summary": summary,
                "description": "Study block created by PaceWise after student confirmation.",
                "start": {"dateTime": start, "timeZone": time_zone},
                "end": {"dateTime": end, "timeZone": time_zone},
                "reminders": {
                    "useDefault": False,
                    "overrides": [{"method": "popup", "minutes": 15}],
                },
                "extendedProperties": {"private": {"pacewiseBlockId": event_id}},
            },
        )
        if response.status_code == 409:
            response = await self._get(
                f"{GOOGLE_CALENDAR_API}/calendars/{quote(calendar_id, safe='')}/events/{event_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        payload = response.json()
        if not payload.get("id"):
            raise GoogleCalendarError("Google did not return the created event")
        return payload

    async def revoke(self, token: str) -> None:
        await self._post(
            GOOGLE_REVOKE_URL,
            data={"token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
