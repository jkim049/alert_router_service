import re
from datetime import datetime
from typing import Annotated, Any, Literal, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --- Conditions ---

class RouteConditions(BaseModel):
    """
    All specified fields must match (AND semantics). Omitted fields match everything.

    - severity: alert.severity must be in this list.
    - service:  alert.service must match at least one entry; glob patterns supported (e.g. "payment-*").
    - group:    alert.group must be in this list.
    - labels:   every key-value pair here must exist in alert.labels (subset match).
    """
    severity: list[str] | None = None
    service: list[str] | None = None
    group: list[str] | None = None
    labels: dict[str, str] | None = None


# --- Active hours ---

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


class ActiveHours(BaseModel):
    timezone: str   # IANA timezone name (e.g. "America/New_York")
    start: str      # "HH:MM" 24-hour format
    end: str        # "HH:MM" 24-hour format

    @field_validator("start", "end")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError("must be in HH:MM format (e.g. '09:00')")
        h, m = int(v[:2]), int(v[3:])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("must be a valid 24-hour time (HH:MM)")
        return v

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, KeyError):
            raise ValueError(f"'{v}' is not a valid IANA timezone")
        return v


# --- Targets (discriminated union on "type") ---

class SlackTarget(BaseModel):
    type: Literal["slack"]
    channel: str


class EmailTarget(BaseModel):
    type: Literal["email"]
    address: str


class PagerDutyTarget(BaseModel):
    type: Literal["pagerduty"]
    service_key: str


class WebhookTarget(BaseModel):
    type: Literal["webhook"]
    url: str
    headers: dict[str, str] = {}


RouteTarget = Annotated[
    Union[SlackTarget, EmailTarget, PagerDutyTarget, WebhookTarget],
    Field(discriminator="type"),
]


# --- Request / response schemas ---

class RouteUpsert(BaseModel):
    """Used for POST /routes — creates or updates a route by id."""
    id: str
    conditions: RouteConditions
    target: RouteTarget
    priority: int
    suppression_window_seconds: int = 0
    active_hours: ActiveHours | None = None

    @field_validator("suppression_window_seconds")
    @classmethod
    def validate_suppression_window(cls, v: int) -> int:
        if v < 0:
            raise ValueError("suppression_window_seconds must be a non-negative integer")
        return v


class RouteUpsertResponse(BaseModel):
    """Response for POST /routes. created=True means new record, False means updated."""
    id: str
    created: bool


class RouteResponse(BaseModel):
    """Full route object returned by GET /routes."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    conditions: RouteConditions
    target: dict[str, Any]
    priority: int
    suppression_window_seconds: int
    active_hours: ActiveHours | None
    created_at: datetime
    updated_at: datetime
