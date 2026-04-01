from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from app.constants import NOTIFICATION_SUPPRESSED

if TYPE_CHECKING:
    from app.models.notification import Notification


class AlertCreate(BaseModel):
    id: str
    severity: Literal["critical", "warning", "info"]
    service: str
    group: str
    description: str = ""
    timestamp: datetime
    labels: dict[str, str] = {}


class AlertRoutedTo(BaseModel):
    route_id: str
    target: dict[str, Any]


class AlertEvaluationDetails(BaseModel):
    total_routes_evaluated: int
    routes_matched: int
    routes_not_matched: int
    suppression_applied: bool


class AlertIngestResponse(BaseModel):
    alert_id: str
    routed_to: AlertRoutedTo | None
    suppressed: bool
    suppression_reason: str | None = None
    matched_routes: list[str]
    evaluation_details: AlertEvaluationDetails

    @classmethod
    def from_notification(cls, notification: Notification) -> AlertIngestResponse:
        matched = notification.matched_route_ids
        return cls(
            alert_id=notification.alert_id,
            routed_to=(
                AlertRoutedTo(**notification.routed_to) if notification.routed_to else None
            ),
            suppressed=notification.status == NOTIFICATION_SUPPRESSED,
            suppression_reason=notification.suppression_reason,
            matched_routes=matched,
            evaluation_details=AlertEvaluationDetails(
                total_routes_evaluated=notification.total_routes_evaluated,
                routes_matched=len(matched),
                routes_not_matched=notification.total_routes_evaluated - len(matched),
                suppression_applied=notification.status == NOTIFICATION_SUPPRESSED,
            ),
        )


class AlertListResponse(BaseModel):
    alerts: list[AlertIngestResponse]
    total: int
