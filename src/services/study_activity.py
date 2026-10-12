"""Transparent activity labels and course-scoped, student-selected rhythms.

Classification describes the work, never a learner's attention or mastery.
Ambiguous work stays unknown and uses the student's default preference.
"""
import re
import unicodedata

ACTIVITY_TYPES = {"concept", "practice", "coding", "review"}


def activity_context(milestone: dict, assignment: dict, task_id: str) -> dict:
    try:
        course_id = int(assignment.get("course_id") or assignment.get("courseId") or task_id.split(":")[0])
        if course_id <= 0:
            course_id = None
    except (TypeError, ValueError):
        course_id = None
    explicit = assignment.get("activity_type") or assignment.get("activityType")
    # Fallback titles append the assignment after a colon; it is context, not
    # the action of this milestone (reading a coding assignment isn't coding).
    text = unicodedata.normalize("NFD", str(milestone.get("title") or "").split(":", 1)[0].lower())
    text = "".join(character for character in text if not unicodedata.combining(character)).replace("đ", "d")
    # Strong action words only; a course named Programming is not itself coding.
    patterns = (
        ("review", r"\b(on tap|on hoc lieu|tu kiem tra|kiem tra lai|review|reassess|retention)\b"),
        ("coding", r"\b(viet code|lap trinh|implement|debug|coding|viet chuong trinh)\b"),
        ("concept", r"\b(doc tai lieu|doc slide|xem hoc lieu|tim hieu khai niem|giai thich|explain|read slides)\b"),
        ("practice", r"\b(lam bai tap|luyen tap|van dung|apply|solve exercises|practice)\b"),
    )
    matches = [kind for kind, pattern in patterns if re.search(pattern, text)]
    if not matches and explicit in ACTIVITY_TYPES:
        return {"courseId": course_id, "activityType": explicit, "activitySource": "assignment_metadata"}
    kind = matches[0] if len(matches) == 1 else "unknown"
    return {"courseId": course_id, "activityType": kind,
            "activitySource": "milestone_action_rule" if kind != "unknown" else "unmapped"}


def effective_rhythm(preferences: dict, course_id: int | None, activity_type: str) -> dict:
    default = {key: preferences.get(key, value) for key, value in (("sessionMinutes", 90), ("breakMinutes", 10))}
    for override in preferences.get("activityRhythms") or []:
        if override.get("courseId") == course_id and override.get("activityType") == activity_type:
            return {key: override[key] for key in default}
    return default
