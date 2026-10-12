"""Native login using the preserved PBKDF2 hashes and live course memberships."""

import base64
import hashlib
import hmac

from fastapi import HTTPException
from sqlalchemy import select

from src.course_source.db import SessionLocal
from src.course_source.models import Course, CourseLifecycle, Enrollment, User


def verify_password(password: str, encoded: str) -> bool:
    try:
        salt_raw, expected_raw = encoded.split(":", 1)
        salt = base64.urlsafe_b64decode(salt_raw.encode())
        expected = base64.urlsafe_b64decode(expected_raw.encode())
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return hmac.compare_digest(actual, expected)


def login(email: str, password: str, course_id: int | None = None) -> dict:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email.strip().lower()))
        # Also perform the expensive hash for unknown users, without disclosing identity.
        dummy = "MDAwMDAwMDAwMDAwMDAwMA==:" + base64.urlsafe_b64encode(bytes(32)).decode()
        valid = verify_password(password, user.password_hash if user else dummy)
        if not user or not valid:
            raise HTTPException(401, "Email hoặc mật khẩu không đúng.")
        if user.role not in {"student", "instructor"}:
            raise HTTPException(403, "Tài khoản không được phép truy cập PaceWise.")
        allowed = db.scalars(
            select(Enrollment.course_id)
            .join(Course, Course.id == Enrollment.course_id)
            .outerjoin(CourseLifecycle, CourseLifecycle.course_id == Course.id)
            .where(Enrollment.user_id == user.id, Enrollment.role == user.role,
                   (CourseLifecycle.archived.is_(False) | CourseLifecycle.course_id.is_(None)))
            .order_by(Enrollment.course_id)
        ).all()
        selected = course_id if course_id is not None else (allowed[0] if allowed else 0)
        if course_id is not None and selected not in allowed:
            raise HTTPException(403, "Bạn không có quyền truy cập môn học này.")
        return {"iss": "pacewise-native", "aud": "pacewise", "sub": str(user.id),
                "course_id": selected, "role": user.role, "name": user.full_name, "email": user.email}
