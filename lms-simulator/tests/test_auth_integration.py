from app.db import Base
from app.models import User
from app.security import _claimed_actor_ids, find_session, hash_password, issue_session
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_database_session_token_is_opaque_and_resolves_user() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(
            email="student@example.test",
            full_name="Test Student",
            password_hash=hash_password("secret"),
            role="student",
            avatar_color="#2563eb",
        )
        db.add(user)
        db.flush()
        access_token, csrf_token, auth_session = issue_session(db, user)
        db.commit()

        assert access_token not in auth_session.token_hash
        assert csrf_token not in auth_session.csrf_hash
        assert find_session(db, access_token).user_id == user.id
        assert find_session(db, "not-the-token") is None


def test_actor_claims_are_detected_in_path_query_and_json() -> None:
    claimed = _claimed_actor_ids(
        "/api/dashboard/7",
        b"user_id=7&course_id=2",
        b'{"sender_id":7,"recipient_ids":[8]}',
        "application/json",
    )

    assert claimed == {7}


def test_target_student_is_not_mistaken_for_acting_user() -> None:
    claimed = _claimed_actor_ids(
        "/api/assignments/3/submissions/99/grade",
        b"",
        b'{"user_id":7,"score":9}',
        "application/json",
    )

    assert claimed == {7}
