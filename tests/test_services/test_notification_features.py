import base64
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import ValidationError
from sqlalchemy import select

from src.config import Settings
from src.db import SessionLocal
from src.persistence_models import NotificationDailyBudget, NotificationJob, UserWorkspace, WebPushSubscription
from src.services.notification_policy import ReminderPreferences, StudyPreferences
from src.services.planning import build_plan_draft
from src.services.reminder_schedule import candidates, reconcile_jobs
from src.services.web_push import (
    deliver_due_reminders,
    recover_notification_leases,
    send_push,
    validate_subscription,
    vapid_keys,
)

NOW = datetime(2026, 10, 9, 3, 0, tzinfo=UTC)  # Friday 10:00 Vietnam


def subscription(endpoint="https://fcm.googleapis.com/fcm/send/test-subscription"):
    key = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    )

    def encode(value):
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    return {"endpoint": endpoint, "keys": {"p256dh": encode(key), "auth": encode(b"0123456789abcdef")}}


def state():
    return {
        "reminders": {"preferences": {"enabled": True, "browserEnabled": True, "pushEnabled": True}},
        "lmsBaseline": {
            "tasks": [
                {
                    "id": "t1",
                    "title": "Relations",
                    "status": "todo",
                    "estimateMin": 120,
                    "loggedMin": 0,
                    "dueAt": "2026-10-12T10:00:00+07:00",
                }
            ],
            "courseData": {},
        },
        "plan": {"blocks": [{"id": "b1", "taskId": "t1", "date": "2026-10-09", "start": "10:15", "end": "11:00"}]},
        "sessions": [],
        "reflections": {},
    }


@pytest.fixture(autouse=True)
def cleanup():
    with SessionLocal() as db:
        for model in (NotificationDailyBudget, NotificationJob, WebPushSubscription):
            db.query(model).delete()
        db.query(UserWorkspace).filter(UserWorkspace.user_id == 9901).delete()
        db.commit()
    yield


def seed(value, count=1):
    with SessionLocal() as db:
        db.add(UserWorkspace(user_id=9901, state_json=json.dumps(value)))
        db.add(
            WebPushSubscription(
                id="device", user_id=9901, session_id="sid", subscription_json=json.dumps(subscription())
            )
        )
        for index in range(count):
            db.add(
                NotificationJob(
                    id=f"job-{index}",
                    user_id=9901,
                    reminder_key=f"r-{index}",
                    kind="study_block",
                    scheduled_at=NOW - timedelta(minutes=1),
                    expires_at=NOW + timedelta(minutes=15),
                    payload_json="{}",
                )
            )
        db.commit()


@pytest.mark.parametrize(
    "instant,expected",
    [
        (datetime(2026, 10, 9, 15, 0, tzinfo=UTC), True),  # 22:00
        (datetime(2026, 10, 9, 23, 59, tzinfo=UTC), True),  # 06:59
        (datetime(2026, 10, 10, 0, 0, tzinfo=UTC), False),  # 07:00
        (NOW, False),
    ],
)
def test_quiet_hours_wrap_midnight(instant, expected):
    assert ReminderPreferences(quietHoursEnabled=True).quiet(instant) is expected


@pytest.mark.parametrize(
    "payload",
    [
        {"dailyCap": 4},
        {"studyBlockLeadMinutes": -1},
        {"quietStart": "25:00"},
        {"quietHoursEnabled": True, "quietStart": "07:00", "quietEnd": "07:00"},
    ],
)
def test_invalid_preferences_rejected(payload):
    with pytest.raises(ValidationError):
        ReminderPreferences.model_validate(payload)


def test_reflect_generated_only_after_do_and_removed_when_saved():
    value = state()
    assert not any(job["kind"] == "reflect_session" for job in candidates(value, NOW))
    value["sessions"] = [{"id": "s1", "taskId": "t1", "blockId": "b1", "minutes": 30, "completedAt": NOW.isoformat()}]
    reflection = next(job for job in candidates(value, NOW) if job["kind"] == "reflect_session")
    assert reflection["at"] == NOW + timedelta(minutes=5)
    assert reflection["href"] == "/reflect?activity=study%3Ab1"
    assert not any(job["kind"] == "study_block" for job in candidates(value, NOW))
    value["reflections"] = {"activity:study:b1": {"scope": "activity", "activityId": "study:b1"}}
    assert not any(job["kind"] == "reflect_session" for job in candidates(value, NOW))


def test_reconcile_is_idempotent_and_cancels_removed_block_without_private_content():
    value = state()
    value["qaMessages"] = [{"text": "SECRET_ANSWER"}]
    with SessionLocal() as db:
        reconcile_jobs(db, 9901, value, NOW)
        db.commit()
        reconcile_jobs(db, 9901, value, NOW)
        db.commit()
        jobs = list(db.scalars(select(NotificationJob)))
        assert len({job.reminder_key for job in jobs}) == len(jobs)
        assert "SECRET_ANSWER" not in " ".join(job.payload_json for job in jobs)
        value["plan"]["blocks"] = []
        reconcile_jobs(db, 9901, value, NOW)
        db.commit()
        assert all(job.status == "cancelled" for job in jobs if job.kind == "study_block")


def test_lms_completion_cannot_be_undone_by_stale_local_progress():
    value = state()
    value["lmsBaseline"]["tasks"][0]["status"] = "done"
    value["taskProgress"] = {"t1": {"status": "in_progress"}}
    assert not any(
        job["kind"].startswith("deadline_") or job["kind"] == "study_block" for job in candidates(value, NOW)
    )


def test_push_uses_same_daily_budget_as_foreground_and_does_not_send_expired_jobs():
    seed(state(), count=4)
    with SessionLocal() as db:
        db.add(NotificationDailyBudget(id="9901:2026-10-09", count=2))
        db.get(NotificationJob, "job-0").expires_at = NOW - timedelta(seconds=1)
        db.commit()
    delivered = []
    assert deliver_due_reminders(Settings(_env_file=None), NOW, sender=lambda *args: delivered.append(args)) == 1
    assert len(delivered) == 1
    with SessionLocal() as db:
        assert db.get(NotificationDailyBudget, "9901:2026-10-09").count == 3
        assert db.get(NotificationJob, "job-0").status == "expired"


def test_inactive_users_do_not_starve_delivery_batch():
    seed(state())
    with SessionLocal() as db:
        db.add(
            UserWorkspace(user_id=9902, state_json=json.dumps({"reminders": {"preferences": {"pushEnabled": False}}}))
        )
        db.add(
            NotificationJob(
                id="inactive",
                user_id=9902,
                reminder_key="inactive",
                kind="deadline_2h",
                priority=0,
                scheduled_at=NOW - timedelta(minutes=1),
                expires_at=NOW + timedelta(minutes=15),
            )
        )
        db.commit()
    sent = []
    assert (
        deliver_due_reminders(
            Settings(_env_file=None, worker_batch_size=1), NOW, sender=lambda *args: sent.append(args)
        )
        == 1
    )
    assert len(sent) == 1
    with SessionLocal() as db:
        db.query(UserWorkspace).filter(UserWorkspace.user_id == 9902).delete()
        db.commit()


def test_concurrent_vapid_initialization_publishes_one_complete_key(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    config = Settings(_env_file=None, webpush_private_key_file=str(tmp_path / "key.pem"))
    with ThreadPoolExecutor(max_workers=8) as pool:
        keys = list(pool.map(lambda _: vapid_keys(config), range(16)))
    assert len(set(keys)) == 1
    assert list(tmp_path.glob(".vapid-*")) == []


def test_push_daily_cap_and_replay_do_not_send_again():
    seed(state(), count=5)
    sent = []
    assert deliver_due_reminders(Settings(_env_file=None), NOW, sender=lambda *args: sent.append(args)) == 3
    assert len(sent) == 3
    assert deliver_due_reminders(Settings(_env_file=None), NOW, sender=lambda *args: sent.append(args)) == 0
    with SessionLocal() as db:
        assert db.get(NotificationDailyBudget, "9901:2026-10-09").count == 3
        db.add(
            NotificationJob(
                id="new-arrival",
                user_id=9901,
                reminder_key="new-arrival",
                kind="deadline_2h",
                scheduled_at=NOW,
                expires_at=NOW + timedelta(hours=1),
                payload_json="{}",
            )
        )
        db.commit()
    assert deliver_due_reminders(Settings(_env_file=None), NOW, sender=lambda *args: sent.append(args)) == 0
    assert len(sent) == 3


def test_active_notification_lease_cannot_be_stolen():
    seed(state())
    with SessionLocal() as db:
        job = db.get(NotificationJob, "job-0")
        job.lease_owner = "notification:other-worker"
        job.heartbeat_at = NOW
        job.lease_expires_at = NOW + timedelta(minutes=2)
        db.commit()

    sent = []
    settings = Settings(_env_file=None)
    assert recover_notification_leases(settings, NOW) == 0
    assert deliver_due_reminders(settings, NOW, sender=lambda *args: sent.append(args)) == 0
    assert sent == []


def test_expired_notification_lease_is_recovered_once():
    seed(state())
    with SessionLocal() as db:
        job = db.get(NotificationJob, "job-0")
        job.lease_owner = "notification:dead-worker"
        job.heartbeat_at = NOW - timedelta(minutes=3)
        job.lease_expires_at = NOW - timedelta(seconds=1)
        db.commit()

    sent = []
    settings = Settings(_env_file=None)
    assert recover_notification_leases(settings, NOW) == 1
    assert deliver_due_reminders(settings, NOW, sender=lambda *args: sent.append(args)) == 1
    assert len(sent) == 1
    assert deliver_due_reminders(settings, NOW, sender=lambda *args: sent.append(args)) == 0


@pytest.mark.parametrize(
    "patch",
    [
        {"enabled": False},
        {"pushEnabled": False},
        {"studyEnabled": False},
        {"quietHoursEnabled": True, "quietStart": "09:00", "quietEnd": "11:00"},
    ],
)
def test_delivery_respects_switches_and_quiet_hours(patch):
    value = state()
    value["reminders"]["preferences"].update(patch)
    seed(value)
    assert deliver_due_reminders(Settings(_env_file=None), NOW, sender=lambda *_: pytest.fail("Must not deliver")) == 0


def test_provider_failure_is_bounded_and_expired_subscription_removed():
    seed(state())

    class GoneError(Exception):
        response = SimpleNamespace(status_code=410)

    def fail(*_):
        raise GoneError("Sensitive provider response")

    assert deliver_due_reminders(Settings(_env_file=None), NOW, sender=fail) == 0
    with SessionLocal() as db:
        assert db.get(WebPushSubscription, "device") is None
        job = db.get(NotificationJob, "job-0")
        assert job.last_error == "Subscription expired"
        assert job.attempts == 1
        assert db.scalar(select(NotificationDailyBudget)).count == 0


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/send",
        "https://127.0.0.1/internal",
        "https://fcm.googleapis.com.evil.test/send",
        "https://fcm.googleapis.com:8443/send",
        "https://user:pass@fcm.googleapis.com/send",
    ],
)
def test_subscription_ssrf_targets_rejected(endpoint):
    with pytest.raises(ValueError):
        validate_subscription(subscription(endpoint))


def test_vapid_key_is_stable_and_production_never_autogenerates(tmp_path):
    settings = Settings(_env_file=None, app_env="test", webpush_private_key_file=str(tmp_path / "key.pem"))
    assert vapid_keys(settings) == vapid_keys(settings)
    production = Settings(_env_file=None, app_env="test", webpush_private_key_file=str(tmp_path / "missing.pem"))
    production.app_env = "production"
    with pytest.raises(ValueError, match="persistent VAPID"):
        vapid_keys(production)


def test_sender_uses_library_with_short_ttl_and_private_key_not_in_payload(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("pywebpush.webpush", lambda **kwargs: captured.update(kwargs))
    config = Settings(_env_file=None, webpush_private_key_file=str(tmp_path / "key.pem"))
    payload = {"title": "PaceWise", "href": "/reflect"}
    send_push(subscription(), payload, config, 120)
    assert json.loads(captured["data"]) == payload
    assert captured["ttl"] == 120 and captured["timeout"] == 10
    assert "PRIVATE KEY" not in captured["data"]


def test_personal_rhythm_controls_new_blocks_and_preserves_lms_constraint():
    draft = build_plan_draft(
        {
            "goal": "Study",
            "tasks": [{"taskId": "a1", "remainingMin": 120}],
            "availability": [{"weekday": 0, "enabled": True, "start": "08:00", "end": "13:00"}],
            "unavailable": [{"weekday": 0, "start": "08:00", "end": "09:00", "source": "lms"}],
            "preferred": "morning",
            "studyPreferences": {"sessionMinutes": 25, "breakMinutes": 5},
        },
        [{"id": "a1", "title": "Assignment", "deadline": "2026-09-28T12:00:00+07:00"}],
        today=date(2026, 9, 28),
    )
    blocks = draft["blocks"]
    assert draft["feasibility"]["feasible"]
    assert blocks[0]["start"] == "09:00" and blocks[0]["end"] == "09:25"
    assert blocks[1]["start"] == "09:30"
    assert all(block["end"] <= "12:00" for block in blocks)
    assert StudyPreferences.model_validate({}).session_minutes == 90
