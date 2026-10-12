"""Validated personal preferences shared by delivery and workspace persistence."""

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReminderPreferences(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    enabled: bool = True
    browser_enabled: bool = Field(default=False, alias="browserEnabled")
    push_enabled: bool = Field(default=False, alias="pushEnabled")
    daily_cap: int = Field(default=3, ge=1, le=3, alias="dailyCap")
    study_lead: int = Field(default=15, ge=0, le=120, alias="studyBlockLeadMinutes")
    digest_hour: int = Field(default=20, ge=0, le=23, alias="digestHour")
    deadline_enabled: bool = Field(default=True, alias="deadlineEnabled")
    study_enabled: bool = Field(default=True, alias="studyEnabled")
    reflect_enabled: bool = Field(default=True, alias="reflectEnabled")
    quiet_enabled: bool = Field(default=False, alias="quietHoursEnabled")
    quiet_start: str = Field(default="22:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$", alias="quietStart")
    quiet_end: str = Field(default="07:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$", alias="quietEnd")

    @model_validator(mode="after")
    def distinct_quiet_hours(self):
        if self.quiet_enabled and self.quiet_start == self.quiet_end:
            raise ValueError("Quiet hours start and end must differ")
        return self

    def quiet(self, now: datetime) -> bool:
        if not self.quiet_enabled:
            return False
        clock = now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%H:%M")
        if self.quiet_start < self.quiet_end:
            return self.quiet_start <= clock < self.quiet_end
        return clock >= self.quiet_start or clock < self.quiet_end

    def allows(self, kind: str) -> bool:
        if not self.enabled:
            return False
        if kind.startswith("deadline_"):
            return self.deadline_enabled
        if kind == "reflect_session":
            return self.reflect_enabled
        return self.study_enabled


class ActivityRhythm(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    course_id: int = Field(gt=0, alias="courseId")
    activity_type: Literal["concept", "practice", "coding", "review"] = Field(alias="activityType")
    session_minutes: int = Field(ge=20, le=120, alias="sessionMinutes")
    break_minutes: int = Field(ge=5, le=30, alias="breakMinutes")


class StudyPreferences(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    session_minutes: int = Field(default=90, ge=20, le=120, alias="sessionMinutes")
    break_minutes: int = Field(default=10, ge=5, le=30, alias="breakMinutes")
    checkpoint_minutes: int = Field(default=0, ge=0, le=15, alias="checkpointMinutes")
    adaptive_suggestions_enabled: bool = Field(default=True, alias="adaptiveSuggestionsEnabled")
    activity_rhythms: list[ActivityRhythm] = Field(default_factory=list, max_length=40, alias="activityRhythms")

    @model_validator(mode="after")
    def unique_activity_scopes(self):
        keys = [(item.course_id, item.activity_type) for item in self.activity_rhythms]
        if len(keys) != len(set(keys)):
            raise ValueError("Each course/activity rhythm must be unique")
        return self
