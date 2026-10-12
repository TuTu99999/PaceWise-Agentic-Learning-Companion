import pytest
from fastapi import HTTPException
from sqlalchemy import select

from src.config import get_settings
from src.db import SessionLocal
from src.persistence_models import KnowledgeStateSnapshot, LearningEvent, LearningEvidenceRecord
from src.security import SessionContext
from src.services.learning_evidence import build_evidence_contract, persist_learning_evidence


def _session() -> SessionContext:
    return SessionContext(
        user_id=99101,
        course_id=88101,
        course_ids=(88101,),
        role="student",
        name="Evidence Test",
        email="evidence@example.edu",
        csrf_hash="test",
        sid="evidence-test",
        exp=4_102_444_800,
    )


def _result(*, hint_level: int = 0, event_key: str = "attempt-1") -> dict:
    return {
        "workflow": "do",
        "status": "completed",
        "query": "Vì quan hệ phản xạ chứa mọi cặp (x, x).",
        "assessment_result": {
            "status": "đã thể hiện được",
            "confidence": "Cao",
            "evaluator_version": "open-rubric-v2",
            "evidence_quotes": ["quan hệ phản xạ chứa mọi cặp (x, x)"],
            "dimensions": {
                "recall": "passed",
                "conceptual": "passed",
                "reasoning": "passed",
                "application": "passed",
                "transfer": "passed",
                "retention": "not_tested",
            },
            "misconceptions": [],
        },
        "request": {
            "assessment_attempt": {
                "response": "Vì quan hệ phản xạ chứa mọi cặp (x, x).",
                "first_attempt": hint_level == 0,
                "hint_level": hint_level,
                "block_id": "block-1",
                "event_key": event_key,
            }
        },
    }


def _trusted(*, mapped: bool = True) -> dict:
    return {
        "question_type": "open",
        "rubric_version": 3,
        "knowledge_component_ids": ["kc-binary-relation"] if mapped else [],
        "kc_provisional": False,
        "cognitive_level": "transfer",
    }


def _clear() -> None:
    session = _session()
    with SessionLocal() as db:
        db.query(KnowledgeStateSnapshot).filter(KnowledgeStateSnapshot.student_user_id == session.user_id).delete()
        db.query(LearningEvent).filter(LearningEvent.student_user_id == session.user_id).delete()
        db.query(LearningEvidenceRecord).filter(LearningEvidenceRecord.student_user_id == session.user_id).delete()
        db.commit()


def test_valid_evidence_creates_one_explainable_knowledge_snapshot_and_is_idempotent():
    _clear()
    session = _session()
    settings = get_settings()
    contract = build_evidence_contract(
        session=session,
        settings=settings,
        result=_result(),
        assessment_id="Q-42",
        trusted_assessment=_trusted(),
    )

    with SessionLocal() as db:
        first_evidence, first_snapshots = persist_learning_evidence(db, session, settings, contract)
        db.commit()
        second_evidence, second_snapshots = persist_learning_evidence(db, session, settings, contract)
        db.commit()
        evidence_rows = db.scalars(
            select(LearningEvidenceRecord).where(LearningEvidenceRecord.student_user_id == session.user_id)
        ).all()
        snapshot_rows = db.scalars(
            select(KnowledgeStateSnapshot).where(KnowledgeStateSnapshot.student_user_id == session.user_id)
        ).all()
        event_rows = db.scalars(select(LearningEvent).where(LearningEvent.student_user_id == session.user_id)).all()

    assert first_evidence["id"] == second_evidence["id"]
    assert first_snapshots == second_snapshots
    assert first_snapshots[0]["knowledge_component"] == "kc-binary-relation"
    assert first_snapshots[0]["level"] == "transfer"
    assert len(evidence_rows) == len(snapshot_rows) == 1
    assert {event.event_type for event in event_rows} == {"ASSESSMENT_COMPLETED", "KNOWLEDGE_STATE_UPDATED"}


def test_unmapped_evidence_is_saved_but_cannot_update_knowledge_state():
    _clear()
    session = _session()
    settings = get_settings()
    contract = build_evidence_contract(
        session=session,
        settings=settings,
        result=_result(event_key="attempt-unmapped"),
        assessment_id="Q-43",
        trusted_assessment=_trusted(mapped=False),
    )

    with SessionLocal() as db:
        evidence, snapshots = persist_learning_evidence(db, session, settings, contract)
        db.commit()

    assert evidence["valid"] is True
    assert evidence["kc_provisional"] is True
    assert evidence["knowledge_component_ids"] == ["unmapped:Q-43"]
    assert snapshots == []


def test_knowledge_snapshots_accumulate_evidence_without_mutating_history():
    _clear()
    session = _session()
    settings = get_settings()
    first = build_evidence_contract(
        session=session,
        settings=settings,
        result=_result(event_key="attempt-cumulative-1"),
        assessment_id="Q-51",
        trusted_assessment=_trusted(),
    )
    second = build_evidence_contract(
        session=session,
        settings=settings,
        result=_result(event_key="attempt-cumulative-2"),
        assessment_id="Q-52",
        trusted_assessment=_trusted(),
    )

    with SessionLocal() as db:
        first_evidence, first_snapshots = persist_learning_evidence(db, session, settings, first)
        db.commit()
        second_evidence, second_snapshots = persist_learning_evidence(db, session, settings, second)
        db.commit()

    assert first_snapshots[0]["evidence_count"] == 1
    assert second_snapshots[0]["evidence_count"] == 2
    assert second_snapshots[0]["source_evidence_ids"] == [
        first_evidence["id"],
        second_evidence["id"],
    ]


def test_heavily_hinted_answer_is_capped_at_conceptual_level():
    session = _session()
    contract = build_evidence_contract(
        session=session,
        settings=get_settings(),
        result=_result(hint_level=4, event_key="attempt-hinted"),
        assessment_id="Q-44",
        trusted_assessment=_trusted(),
    )

    assert contract["demonstrated_level"] == "conceptual"
    assert contract["first_attempt"] is False


def test_correct_closed_answer_only_proves_recognition():
    result = _result(event_key="attempt-closed")
    result["assessment_result"]["dimensions"] = {
        "recall": "passed",
        "conceptual": "not_tested",
        "application": "not_tested",
        "transfer": "not_tested",
        "retention": "not_tested",
    }
    trusted = _trusted()
    trusted["question_type"] = "closed"
    trusted["cognitive_level"] = "conceptual"

    contract = build_evidence_contract(
        session=_session(),
        settings=get_settings(),
        result=result,
        assessment_id="Q-45",
        trusted_assessment=trusted,
    )

    assert contract["demonstrated_level"] == "recognition"


def test_missing_evidence_is_explicitly_insufficient_and_cannot_update_state():
    result = _result(event_key="attempt-no-evidence")
    result["assessment_result"]["evidence_quotes"] = []
    contract = build_evidence_contract(
        session=_session(),
        settings=get_settings(),
        result=result,
        assessment_id="Q-46",
        trusted_assessment=_trusted(),
    )

    assert contract["status"] == "insufficient_evidence"
    assert contract["demonstrated_level"] == "no_evidence"
    assert contract["can_update_knowledge"] is False


def test_same_retry_key_cannot_replay_another_response():
    _clear()
    session = _session()
    settings = get_settings()
    contract = build_evidence_contract(
        session=session,
        settings=settings,
        result=_result(event_key="retry-conflict"),
        assessment_id="Q-1",
        trusted_assessment=_trusted(),
    )
    with SessionLocal() as db:
        persist_learning_evidence(db, session, settings, contract)
        db.commit()
        with pytest.raises(HTTPException) as error:
            persist_learning_evidence(db, session, settings, {**contract, "response": "another response"})
        assert error.value.status_code == 409
