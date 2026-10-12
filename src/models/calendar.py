"""Shared validation models for external calendar exports."""

from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, Field, model_validator


class CalendarBlock(BaseModel):
    block_id: str = Field(alias="blockId", min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def validate_duration(self) -> "CalendarBlock":
        if self.end <= self.start:
            raise ValueError("Block end must be after start")
        if self.end - self.start > timedelta(hours=12):
            raise ValueError("A study block cannot exceed 12 hours")
        return self


class GoogleEventExportRequest(BaseModel):
    confirmed: bool
    time_zone: str = Field(default="Asia/Ho_Chi_Minh", alias="timeZone", max_length=64)
    blocks: list[CalendarBlock] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_time_zone(self) -> "GoogleEventExportRequest":
        try:
            ZoneInfo(self.time_zone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unsupported time zone") from exc
        return self


class IcsExportRequest(BaseModel):
    calendar_name: str = Field(default="PaceWise Study Plan", alias="calendarName", min_length=1, max_length=100)
    blocks: list[CalendarBlock] = Field(min_length=1, max_length=100)
