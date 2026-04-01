from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants import NOTIFICATION_PENDING, NOTIFICATION_SUPPRESSED, NOTIFICATION_UNROUTED
from app.database import get_db, utcnow
from app.models import Alert, Route, SuppressionRecord, Notification
from app import schemas
from app import engine as rule_engine

router = APIRouter(tags=["Alerts"])


@router.post("/alerts", response_model=schemas.AlertIngestResponse, status_code=200)
def ingest_alert(payload: schemas.AlertCreate, db: Session = Depends(get_db)):
    now = utcnow()

    # Upsert alert
    alert = db.get(Alert, payload.id)
    if alert:
        alert.severity = payload.severity
        alert.service = payload.service
        alert.group = payload.group
        alert.description = payload.description
        alert.timestamp = payload.timestamp
        alert.labels = payload.labels
        alert.updated_at = now
    else:
        alert = Alert(**payload.model_dump())
        db.add(alert)
    db.flush()

    # Evaluate all routes
    all_routes = db.query(Route).all()
    matched = rule_engine.evaluate(alert, all_routes)
    matched_ids = [r.id for r in matched]

    # Pre-load active suppression records for all matched routes in one query
    active_suppressions: dict[str, object] = {}
    if matched_ids:
        recs = (
            db.query(SuppressionRecord)
            .filter(
                SuppressionRecord.route_id.in_(matched_ids),
                SuppressionRecord.service == alert.service,
                SuppressionRecord.suppressed_until > now,
            )
            .all()
        )
        active_suppressions = {rec.route_id: rec.suppressed_until for rec in recs}

    result = rule_engine.resolve_winner(matched, active_suppressions, alert.service)
    winner = result.winner

    # Write suppression record for the winning (unsuppressed) route
    if winner and not result.suppressed and winner.suppression_window_seconds > 0:
        suppressed_until = now + timedelta(seconds=winner.suppression_window_seconds)
        existing_rec = (
            db.query(SuppressionRecord)
            .filter(
                SuppressionRecord.route_id == winner.id,
                SuppressionRecord.service == alert.service,
            )
            .first()
        )
        if existing_rec:
            existing_rec.suppressed_until = suppressed_until
        else:
            db.add(SuppressionRecord(
                route_id=winner.id,
                service=alert.service,
                suppressed_until=suppressed_until,
            ))

    routed_to = (
        schemas.AlertRoutedTo(route_id=winner.id, target=winner.target) if winner else None
    )

    db.add(Notification(
        alert_id=alert.id,
        route_id=winner.id if winner else None,
        channel=winner.target.get("type") if winner else None,
        status=result.notification_status,
        routed_to={"route_id": winner.id, "target": winner.target} if winner else None,
        matched_route_ids=matched_ids,
        total_routes_evaluated=len(all_routes),
        suppression_reason=result.suppression_reason,
    ))
    db.commit()

    return schemas.AlertIngestResponse(
        alert_id=alert.id,
        routed_to=routed_to,
        suppressed=result.suppressed,
        suppression_reason=result.suppression_reason,
        matched_routes=matched_ids,
        evaluation_details=schemas.AlertEvaluationDetails(
            total_routes_evaluated=len(all_routes),
            routes_matched=len(matched),
            routes_not_matched=len(all_routes) - len(matched),
            suppression_applied=result.suppression_applied,
        ),
    )


@router.get("/alerts", response_model=schemas.AlertListResponse)
def list_alerts(
    service: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    routed: bool | None = Query(default=None),
    suppressed: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    # Subquery: latest notification ID per alert (max id = most recent)
    latest_subq = (
        db.query(
            Notification.alert_id,
            func.max(Notification.id).label("max_id"),
        )
        .group_by(Notification.alert_id)
        .subquery()
    )

    query = (
        db.query(Alert, Notification)
        .join(latest_subq, Alert.id == latest_subq.c.alert_id)
        .join(Notification, Notification.id == latest_subq.c.max_id)
    )

    if service is not None:
        query = query.filter(Alert.service == service)
    if severity is not None:
        query = query.filter(Alert.severity == severity)
    if routed is not None:
        if routed:
            query = query.filter(Notification.status.in_([NOTIFICATION_PENDING, NOTIFICATION_SUPPRESSED]))
        else:
            query = query.filter(Notification.status == NOTIFICATION_UNROUTED)
    if suppressed is not None:
        if suppressed:
            query = query.filter(Notification.status == NOTIFICATION_SUPPRESSED)
        else:
            query = query.filter(Notification.status != NOTIFICATION_SUPPRESSED)

    results = query.order_by(Alert.id.asc()).all()

    alerts = [
        schemas.AlertIngestResponse.from_notification(notification)
        for _, notification in results
    ]

    return schemas.AlertListResponse(alerts=alerts, total=len(alerts))


@router.get("/alerts/{alert_id}", response_model=schemas.AlertIngestResponse)
def get_alert(alert_id: str, db: Session = Depends(get_db)):
    if not db.get(Alert, alert_id):
        return JSONResponse(status_code=404, content={"error": "alert not found"})

    notification = (
        db.query(Notification)
        .filter(Notification.alert_id == alert_id)
        .order_by(Notification.id.desc())
        .first()
    )
    if not notification:
        return JSONResponse(status_code=404, content={"error": "alert not found"})

    return schemas.AlertIngestResponse.from_notification(notification)
