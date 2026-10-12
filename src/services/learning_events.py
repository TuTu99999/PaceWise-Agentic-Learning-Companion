"""Scoped, idempotent audit events shared by Plan, Do and Reflect."""

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import Settings
from src.persistence_models import LearningEvent
from src.security import SessionContext


def audit(
    db: Session, session: SessionContext, settings: Settings, kind: str, entity_id: str, key: str, payload: dict
) -> None:
    event_key = hashlib.sha256(
        f"{settings.institution_id}:{session.user_id}:{session.course_id}:{kind}:{key}".encode()
    ).hexdigest()
    if not db.scalar(select(LearningEvent.id).where(LearningEvent.event_key == event_key)):
        db.add(
            LearningEvent(
                id=f"EV-{uuid.uuid4().hex[:20]}",
                event_key=event_key,
                institution_id=settings.institution_id,
                student_user_id=session.user_id,
                course_id=session.course_id,
                event_type=kind,
                entity_id=entity_id,
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
        )
        db.flush()
