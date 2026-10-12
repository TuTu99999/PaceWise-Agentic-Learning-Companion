from datetime import UTC, datetime

from src.agents.tools.schedule_calculator import (
    _extract_slot_duration,
    _parse_iso_datetime,
    _parse_time_str,
    _slot_bounds,
    calculate_available_hours,
    check_deadline_slack,
    detect_schedule_conflicts,
)


def test_unavailable_different_day_is_not_subtracted():
    available = [{"day": "monday", "start": "18:00", "end": "20:00"}]
    unavailable = [{"day": "tuesday", "start": "18:00", "end": "19:00"}]
    assert calculate_available_hours(available, unavailable) == 2.0


def test_only_overlap_is_subtracted():
    available = [{"day": "monday", "start": "18:00", "end": "21:00"}]
    unavailable = [{"day": "monday", "start": "19:00", "end": "20:00"}]
    assert calculate_available_hours(available, unavailable) == 2.0


def test_overlapping_busy_slots_are_not_double_counted():
    available = [{"day": "monday", "start": "18:00", "end": "22:00"}]
    unavailable = [
        {"day": "monday", "start": "19:00", "end": "21:00"},
        {"day": "monday", "start": "20:00", "end": "21:30"},
    ]
    assert calculate_available_hours(available, unavailable) == 1.5


def test_numeric_unavailability_is_conservative():
    assert calculate_available_hours([{"hours": 4}], [{"hours": 1.5}]) == 2.5


def test_z_deadline_supports_timezone_aware_math():
    result = check_deadline_slack(
        "2026-09-29T12:00:00Z",
        2,
        current_time=datetime(2026, 9, 29, 8, 0, tzinfo=UTC),
    )
    assert result["hours_until_deadline"] == 4.0
    assert result["slack_hours"] == 2.0


def test_schedule_conflict_respects_day():
    slots = [
        {"id": "a", "day": "monday", "start_time": "09:00", "end_time": "10:00"},
        {"id": "b", "day": "tuesday", "start_time": "09:00", "end_time": "10:00"},
    ]
    assert detect_schedule_conflicts(slots) == []


def test_schedule_conflict_detected():
    slots = [
        {"id": "a", "day": "monday", "start_time": "09:00", "end_time": "10:30"},
        {"id": "b", "day": "monday", "start_time": "10:00", "end_time": "11:00"},
    ]
    assert len(detect_schedule_conflicts(slots)) == 1


def test_time_and_duration_parsers_cover_invalid_numeric_and_overnight_slots():
    assert _parse_time_str("invalid") is None
    now = datetime(2026, 10, 2, 8, 0)
    assert _parse_iso_datetime(now) is now
    assert _parse_iso_datetime(42) is None
    assert _extract_slot_duration(1.5) == 1.5
    assert _extract_slot_duration(object()) == 0
    assert _extract_slot_duration({"hours": "invalid"}) == 0
    assert _extract_slot_duration({"start": 9, "end": 11.5}) == 2.5
    assert _extract_slot_duration(
        {"start": "2026-10-02T09:00:00", "end": "2026-10-02T10:30:00"}
    ) == 1.5
    assert _extract_slot_duration({"start": "23:00", "end": "01:00"}) == 2
    assert _extract_slot_duration({"start": "bad", "end": "worse"}) == 0


def test_slot_bounds_support_numeric_iso_invalid_and_overnight_values():
    assert _slot_bounds({"day": "Monday", "start": 9, "end": 11}) == ("monday", 9, 11)
    iso = _slot_bounds(
        {"start": "2026-10-02T09:00:00+07:00", "end": "2026-10-02T10:00:00+07:00"}
    )
    assert iso and iso[0] == "2026-10-02"
    assert _slot_bounds({"start": "bad", "end": "worse"}) is None
    overnight = _slot_bounds({"day": "Friday", "start": "23:00", "end": "01:00"})
    assert overnight == ("friday", 23, 25)


def test_available_hours_ignore_unpositioned_entries_and_invalid_busy_slots():
    availability = [
        2,
        {"hours": 1},
        {"day": "monday", "start": "18:00", "end": "20:00"},
        {"label": "missing bounds"},
    ]
    unavailable = [object(), {"start": "bad", "end": "worse"}, {"hours": 0.5}]
    assert calculate_available_hours(availability, unavailable) == 4.5


def test_deadline_slack_supports_relative_invalid_and_timezone_mismatch_inputs():
    assert check_deadline_slack(1, 2)["risk_level"] == "critical"
    assert check_deadline_slack("3.5", 2)["risk_level"] == "high"
    assert check_deadline_slack("not-a-deadline", 0)["hours_until_deadline"] == 0

    aware_now = datetime(2026, 10, 2, 8, 0, tzinfo=UTC)
    naive_deadline = check_deadline_slack("2026-10-02T12:00:00", 1, aware_now)
    assert naive_deadline["risk_level"] == "safe"
    aware_deadline = check_deadline_slack(
        "2026-10-02T12:00:00+00:00",
        1,
        datetime(2026, 10, 2, 8, 0),
    )
    assert aware_deadline["slack_hours"] == 3


def test_conflict_detection_supports_iso_numeric_and_incomplete_slots():
    assert detect_schedule_conflicts(None) == []
    slots = [
        {"title": "ignored"},
        {"id": "iso-a", "start": "2026-10-02T09:00:00Z", "end": "2026-10-02T11:00:00Z"},
        {"id": "iso-b", "start": "2026-10-02T10:00:00Z", "end": "2026-10-02T12:00:00Z"},
        {"id": "num-a", "day": "monday", "start": 9, "end": 11},
        {"id": "num-b", "day": "monday", "start": 10, "end": 12},
    ]
    conflicts = detect_schedule_conflicts(slots)
    assert {item["slot_1"]["id"] for item in conflicts} == {"iso-a", "num-a"}
