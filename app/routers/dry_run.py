from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db, utcnow
from app.models import Alert, Route, SuppressionRecord
from app import schemas
from app import evaluator as rule_engine

router = APIRouter(tags=["Test"])


@router.post("/test", response_model=schemas.AlertIngestResponse, status_code=200)
def test_alert(payload: schemas.AlertCreate, db: Session = Depends(get_db)):
    """Dry-run: evaluate an alert against current routes with no side effects."""
    now = utcnow()

    # Build a transient Alert for the engine — never added to the session
    alert = Alert(**payload.model_dump())

    all_routes = db.query(Route).all()
    matched = rule_engine.evaluate(alert, all_routes)
    matched_ids = [r.id for r in matched]

    # Pre-load active suppression records for all matched routes in one query
    active_suppressions: dict[str, datetime] = {}
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

    routed_to = (
        schemas.AlertRoutedTo(route_id=winner.id, target=winner.target) if winner else None
    )

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
