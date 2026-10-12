import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import pytest

from src.config import Settings
from src.db import SessionLocal
from src.persistence_models import GoogleQuotaState
from src.services.calendar_quota import CalendarQuotaExceeded, operation_slot, release, reserve


@pytest.fixture(autouse=True)
def clean_quota():
    with SessionLocal() as db:
        db.query(GoogleQuotaState).delete()
        db.commit()


def limits(**kwargs):
    return Settings(_env_file=None, **kwargs)


def test_minute_limits_do_not_reset_at_window_boundary_and_daily_is_hard():
    settings = limits(google_api_project_per_minute=3, google_api_user_per_minute=2, google_api_daily_budget=4)
    for _ in range(2):
        release(reserve(settings, 1, now=3599))
    with pytest.raises(CalendarQuotaExceeded):
        reserve(settings, 1, now=3601)
    release(reserve(settings, 2, now=3601))
    with pytest.raises(CalendarQuotaExceeded):
        reserve(settings, 3, now=3601)
    release(reserve(settings, 3, now=3721))
    with pytest.raises(CalendarQuotaExceeded) as capped:
        reserve(settings, 4, now=7321)
    assert capped.value.status_code == 429
    release(reserve(settings, 4, now=25 * 3600))


def test_operation_lock_is_per_user_and_shared_not_process_local():
    settings = limits()
    lease = operation_slot(settings, 1, acquire=True)
    with pytest.raises(CalendarQuotaExceeded):
        operation_slot(settings, 1, acquire=True)
    other = operation_slot(settings, 2, acquire=True)
    operation_slot(settings, 1, acquire=False, lease="wrong")
    with pytest.raises(CalendarQuotaExceeded):
        operation_slot(settings, 1, acquire=True)
    operation_slot(settings, 1, acquire=False, lease=lease)
    operation_slot(settings, 2, acquire=False, lease=other)
    operation_slot(settings, 1, acquire=True)


def test_limiter_store_failure_is_fail_closed(monkeypatch):
    from fastapi import HTTPException
    from sqlalchemy.exc import SQLAlchemyError

    def broken():
        raise SQLAlchemyError("password=DO_NOT_EXPORT")

    monkeypatch.setattr("src.services.calendar_quota.SessionLocal", broken)
    with pytest.raises(HTTPException) as failed:
        reserve(limits(), 1)
    assert failed.value.status_code == 503 and "DO_NOT_EXPORT" not in str(failed.value.detail)


def test_1000_contending_requests_share_budget_and_bound_external_work():
    settings = limits(google_api_max_concurrent=4, google_api_daily_budget=40)
    active = peak = accepted = 0
    lock = Lock()

    def request(user):
        nonlocal active, peak, accepted
        try:
            lease = reserve(settings, user)
        except CalendarQuotaExceeded:
            return "limited"
        try:
            with lock:
                active += 1
                peak = max(peak, active)
                accepted += 1
            time.sleep(0.02)  # Fake outbound provider, no Google traffic.
            with lock:
                active -= 1
            return "accepted"
        finally:
            release(lease)

    with ThreadPoolExecutor(max_workers=32) as executor:
        outcomes = list(executor.map(request, range(1000)))
    assert accepted <= 40 and peak <= 4 and active == 0
    assert len(outcomes) == 1000 and outcomes.count("limited") >= 960
    with SessionLocal() as db:
        state = json.loads(db.get(GoogleQuotaState, "google-api").state_json)
    assert sum(state["hours"].values()) == accepted and state["leases"] == {}
    print(
        {
            "requests": 1000,
            "workers": 32,
            "accepted": accepted,
            "limited": outcomes.count("limited"),
            "peak": peak,
            "real_google": False,
        }
    )
