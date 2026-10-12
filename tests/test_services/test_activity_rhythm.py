from datetime import date

import pytest
from pydantic import ValidationError

from src.services.notification_policy import StudyPreferences
from src.services.plan_intelligence import estimate_workload
from src.services.planning import build_plan_draft
from src.services.study_activity import activity_context, effective_rhythm
from src.services.study_rhythm import compare_rhythm_trial, propose_rhythm


def sample(index, **patch):
    return {"session_id": f"s{index}", "course_id": 1, "task_id": "1:a", "activity_type": "concept",
            "readiness_key": "k1", "rhythm": {"sessionMinutes": 60, "breakMinutes": 10},
            "time_source": "timer", "actual_minutes": 60, "planned_minutes": 60, "completion_percent": 100,
            "length_feeling": "too_long", "interruption_reason": "none", "recorded_at": str(index), **patch}


def prefs():
    return {"sessionMinutes": 90, "breakMinutes": 10, "activityRhythms": [
        {"courseId": 1, "activityType": "concept", "sessionMinutes": 60, "breakMinutes": 10},
        {"courseId": 1, "activityType": "coding", "sessionMinutes": 75, "breakMinutes": 5}]}


@pytest.mark.parametrize("title,kind", [("Đọc slide quan hệ", "concept"), ("Viết code xử lý quan hệ", "coding"),
    ("Làm bài tập quan hệ", "practice"), ("Ôn tập chương 3", "review"), ("Làm báo cáo", "unknown"),
    ("Đọc slide và viết code", "unknown")])
def test_action_mapping_is_transparent_and_abstains_when_ambiguous(title, kind):
    context = activity_context({"title": title}, {}, "1:a")
    assert context["activityType"] == kind and context["courseId"] == 1


def test_scope_defaults_metadata_and_validation():
    assert effective_rhythm(prefs(), 1, "concept")["sessionMinutes"] == 60
    assert effective_rhythm(prefs(), 1, "coding")["sessionMinutes"] == 75
    assert effective_rhythm(prefs(), 2, "concept")["sessionMinutes"] == 90
    assert effective_rhythm(prefs(), 1, "unknown")["sessionMinutes"] == 90
    assert activity_context({}, {"activity_type": "coding"}, "not-scoped")["courseId"] is None
    assert StudyPreferences.model_validate(prefs()).activity_rhythms[0].activity_type == "concept"
    with pytest.raises(ValidationError):
        StudyPreferences.model_validate({**prefs(), "activityRhythms": prefs()["activityRhythms"] * 2})
    with pytest.raises(ValidationError):
        StudyPreferences.model_validate({**prefs(), "activityRhythms": [{**prefs()["activityRhythms"][0], "activityType": "unknown"}]})


def test_three_similar_fatigued_half_sessions_can_propose_but_not_one():
    rows = [sample(i, actual_minutes=30, interruption_reason="fatigue", completion_percent=50) for i in range(3)]
    assert propose_rhythm(rows[:1], prefs())["proposal"] is None
    proposal = propose_rhythm(rows, prefs())["proposal"]
    assert proposal["activityType"] == "concept" and proposal["courseId"] == 1
    assert proposal["preferences"]["sessionMinutes"] == 45
    assert proposal["learningQuality"] == "not_comparatively_validated"
    assert prefs()["sessionMinutes"] == 90


@pytest.mark.parametrize("patch", [{"activity_type": "coding"}, {"activity_type": "unknown"}, {"activity_type": None},
                                  {"course_id": 2}, {"interruption_reason": "unexpected"}])
def test_no_cross_context_or_unknown_activity_suggestion(patch):
    assert propose_rhythm([sample(1), sample(2), sample(3, **patch)], prefs())["proposal"] is None


def test_workload_does_not_borrow_coding_history_for_concept_work():
    rows = [sample(i, activity_type="coding", actual_minutes=120) for i in range(3)]
    assert estimate_workload(30, learner_profile={"do_history": rows}, task_id="1:a", activity_type="concept").p50_minutes == 30
    assert estimate_workload(30, learner_profile={"do_history": rows}, task_id="1:a", activity_type="coding").p50_minutes == 53  # bounded factor 1.75


def test_trial_deduplicates_and_excludes_other_activity_and_checkpoint_budget():
    before = [sample(i) for i in range(3)]
    trial = {**propose_rhythm(before, prefs())["proposal"], "accepted_at": "2026-10-10"}
    after = sample(4, rhythm=trial["preferences"], recorded_at="2026-10-11")
    rows = before + [after] * 4 + [sample(5, activity_type="coding", rhythm=trial["preferences"], recorded_at="2026-10-11"),
                                  sample(6, checkpoint_minutes=5, rhythm=trial["preferences"], recorded_at="2026-10-11")]
    result = compare_rhythm_trial(rows, trial)
    assert result["after"]["sessions"] == 1 and result["status"] == "collecting"
    assert result["after"]["assessment"]["retention"]["passRate"] is None


def test_already_short_blocks_or_missing_planned_duration_do_not_shorten_cap():
    for planned in [None, 20, 45]:
        rows = [sample(i, planned_minutes=planned or 0, actual_minutes=30, interruption_reason="fatigue") for i in range(3)]
        assert propose_rhythm(rows, prefs())["proposal"] is None


@pytest.mark.parametrize("patch", [{"actual_minutes": None}, {"planned_minutes": None}, {"actual_minutes": float("nan")}, {"actual_minutes": "60"}])
def test_malformed_legacy_duration_abstains_instead_of_crashing(patch):
    assert propose_rhythm([sample(i, **patch) for i in range(3)], prefs())["proposal"] is None


def test_comparison_distinguishes_assisted_answers_and_missing_retention():
    before = [sample(i, hint_count=2, assessment_summary={"conceptual": "failed"}) for i in range(3)]
    trial = {**propose_rhythm(before, prefs())["proposal"], "accepted_at": "2026-10-10"}
    after = [sample(i, hint_count=0, rhythm=trial["preferences"], recorded_at="2026-10-11",
                    assessment_summary={"conceptual": "passed", "application": "failed"}) for i in range(3, 6)]
    result = compare_rhythm_trial(before + after, trial)
    assert result["before"]["assistedAssessmentRate"] == 1
    assert result["after"]["assistedAssessmentRate"] == 0
    assert result["after"]["assessment"]["application"]["passRate"] == 0
    assert result["after"]["assessment"]["retention"]["passRate"] is None
    assert result["status"] == "descriptive_not_causal"


def plan_input(course=1):
    return {"weekStart": "2026-10-05", "tasks": [{"taskId": f"{course}:a", "remainingMin": 120}],
            "availability": [{"weekday": 5, "enabled": True, "start": "15:00", "end": "19:00"}],
            "studyPreferences": prefs()}


@pytest.mark.parametrize("course,kind,minutes", [(1, "concept", 60), (1, "coding", 75), (2, "concept", 90), (1, "unknown", 90)])
def test_scheduler_uses_course_activity_and_never_reduces_total_work(course, kind, minutes):
    draft = build_plan_draft(plan_input(course), [{"id": f"{course}:a", "activity_type": kind,
        "deadline": "2026-10-10T19:00:00+07:00"}], today=date(2026, 10, 10))
    assert sum(block["workMinutes"] for block in draft["blocks"]) == 120
    assert all(block["workMinutes"] <= minutes and block["rhythm"]["sessionMinutes"] == minutes for block in draft["blocks"])
    assert draft["feasibility"]["feasible"]


def test_scoped_rhythm_checkpoint_and_break_respect_exact_deadline():
    data = plan_input()
    data["studyPreferences"]["checkpointMinutes"] = 15
    data["studyPreferences"]["activityRhythms"][0]["sessionMinutes"] = 20
    data["tasks"][0]["remainingMin"] = 10
    data["availability"][0]["end"] = "15:50"
    draft = build_plan_draft(data, [{"id": "1:a", "activity_type": "concept", "deadline": "2026-10-10T15:50:00+07:00"}], today=date(2026, 10, 10))
    assert draft["blocks"][0]["end"] == "15:20"
    assert draft["blocks"][1]["end"] == "15:50"  # includes the 10-minute break
    assert sum(block["workMinutes"] for block in draft["blocks"]) == 10
    data["availability"][0]["end"] = "15:30"
    blocked = build_plan_draft(data, [{"id": "1:a", "activity_type": "concept", "deadline": "2026-10-10T15:30:00+07:00"}], today=date(2026, 10, 10))
    assert not blocked["feasibility"]["feasible"]


def test_ninety_minutes_is_a_session_cap_and_a_seventy_minute_tail_keeps_all_work():
    draft = build_plan_draft(
        {
            "weekStart": "2026-10-05",
            "tasks": [{"taskId": "1:a", "remainingMin": 160}],
            "availability": [{"weekday": 0, "enabled": True, "start": "08:00", "end": "12:00"}],
            "unavailable": [],
            "preferred": ["morning"],
            "studyPreferences": {"sessionMinutes": 90, "breakMinutes": 10},
        },
        [{"id": "1:a", "course_id": 1, "title": "Bài tập", "deadline": "2026-10-05T12:00:00+07:00"}],
        proposed_milestones=[{
            "milestone_id": "1:a:complete",
            "task_id": "1:a",
            "title": "Làm bài tập",
            "estimated_minutes": 160,
        }],
        today=date(2026, 10, 5),
    )

    agent_blocks = [block for block in draft["blocks"] if block["placementSource"] == "agent"]
    assert [block["workMinutes"] for block in agent_blocks] == [90, 70]
    assert all(block["rhythm"]["sessionMinutes"] == 90 for block in agent_blocks)
    assert sum(block["workMinutes"] for block in agent_blocks) == 160
    assert draft["planningTargets"][0]["targetMin"] == 160
    assert draft["feasibility"]["feasible"]
    assert any("không làm giảm tổng công việc" in reason for reason in draft["reasons"])


def test_replan_keeps_ninety_minute_cap_sleep_bounds_and_student_pin():
    draft = build_plan_draft(
        {
            "weekStart": "2026-10-05",
            "tasks": [{"taskId": "1:a", "remainingMin": 180}],
            # This is the frontend's routine-derived full-day envelope. Sleep
            # and the newly added busy interval carve out usable capacity.
            "availability": [{"weekday": 0, "enabled": True, "start": "00:00", "end": "24:00"}],
            "unavailable": [
                {"weekday": 0, "start": "00:00", "end": "08:00", "category": "sleep"},
                {"weekday": 0, "start": "13:00", "end": "24:00", "category": "sleep"},
                {"date": "2026-10-05", "weekday": 0, "start": "09:00", "end": "10:30", "category": "other"},
            ],
            "preferred": ["morning"],
            "studyPreferences": {"sessionMinutes": 90, "breakMinutes": 10},
            "pinnedBlocks": [
                {"id": "student-pin", "taskId": "1:a", "date": "2026-10-05", "start": "08:00", "end": "09:00", "placementSource": "student"},
                {"id": "old-agent", "taskId": "1:a", "date": "2026-10-05", "start": "09:00", "end": "10:30", "placementSource": "agent"},
            ],
        },
        [{"id": "1:a", "course_id": 1, "title": "Bài tập", "deadline": "2026-10-05T13:00:00+07:00"}],
        today=date(2026, 10, 5),
    )

    assert any(block["id"] == "student-pin" for block in draft["blocks"])
    assert not any(block["id"] == "old-agent" for block in draft["blocks"])
    generated = [block for block in draft["blocks"] if block["placementSource"] == "agent"]
    assert generated
    assert all(block["rhythm"]["sessionMinutes"] == 90 for block in generated)
    assert all("08:00" <= block["start"] < block["end"] <= "13:00" for block in draft["blocks"])
    assert all(not (block["start"] < "10:30" and "09:00" < block["end"]) for block in generated)
    assert 60 + sum(block["workMinutes"] for block in generated) == 180
    assert draft["feasibility"]["feasible"]
