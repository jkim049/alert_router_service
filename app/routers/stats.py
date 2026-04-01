from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants import NOTIFICATION_PENDING, NOTIFICATION_SUPPRESSED
from app.database import get_db
from app.models import Alert, Notification
from app import schemas

router = APIRouter(tags=["Stats"])


@router.get("/stats", response_model=schemas.StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    status_counts = (
        db.query(Notification.status, func.count(Notification.id))
        .group_by(Notification.status)
        .all()
    )
    status_map = {status: count for status, count in status_counts}
    total_routed = status_map.get(NOTIFICATION_PENDING, 0)
    total_suppressed = status_map.get(NOTIFICATION_SUPPRESSED, 0)
    total_unrouted = status_map.get("unrouted", 0)

    severity_rows = (
        db.query(Alert.severity, func.count(Notification.id))
        .join(Notification, Alert.id == Notification.alert_id)
        .group_by(Alert.severity)
        .all()
    )
    by_severity = {severity: count for severity, count in severity_rows}

    route_rows = (
        db.query(Notification.route_id, Notification.status, func.count(Notification.id))
        .filter(Notification.route_id.isnot(None))
        .group_by(Notification.route_id, Notification.status)
        .all()
    )
    by_route: dict[str, dict] = {}
    for route_id, status, count in route_rows:
        if route_id not in by_route:
            by_route[route_id] = {"total_matched": 0, "total_routed": 0, "total_suppressed": 0}
        by_route[route_id]["total_matched"] += count
        if status == NOTIFICATION_PENDING:
            by_route[route_id]["total_routed"] += count
        elif status == NOTIFICATION_SUPPRESSED:
            by_route[route_id]["total_suppressed"] += count

    service_rows = (
        db.query(Alert.service, func.count(Notification.id))
        .join(Notification, Alert.id == Notification.alert_id)
        .group_by(Alert.service)
        .all()
    )
    by_service = {service: count for service, count in service_rows}

    return schemas.StatsResponse(
        total_alerts_processed=total_routed + total_suppressed + total_unrouted,
        total_routed=total_routed,
        total_suppressed=total_suppressed,
        total_unrouted=total_unrouted,
        by_severity=by_severity,
        by_route={rid: schemas.RouteStats(**stats) for rid, stats in by_route.items()},
        by_service=by_service,
    )
