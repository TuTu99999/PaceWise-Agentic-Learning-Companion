"""Reversible removal of course calendar entries, never their graded tasks."""

LESSON_KINDS = ("class", "class_session")
SCHEDULE_KINDS = (*LESSON_KINDS, "lecture_video", "quiz", "midterm", "final_exam")
REMOVED_SCHEDULE_KINDS = tuple("removed_" + kind for kind in SCHEDULE_KINDS)


def remove_calendar_kind(kind: str) -> str:
    if kind not in SCHEDULE_KINDS:
        raise ValueError("Only course schedule entries can be removed")
    return "removed_" + kind
