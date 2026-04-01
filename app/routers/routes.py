from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db, utcnow
from app.models import Route
from app import schemas

router = APIRouter(tags=["Routes"])


@router.post("/routes", response_model=schemas.RouteUpsertResponse, status_code=200)
def upsert_route(payload: schemas.RouteUpsert, db: Session = Depends(get_db)):
    conditions_data = payload.conditions.model_dump(exclude_none=True)
    target_data = payload.target.model_dump()
    active_hours_data = payload.active_hours.model_dump() if payload.active_hours else None

    existing = db.get(Route, payload.id)

    if existing:
        existing.conditions = conditions_data
        existing.target = target_data
        existing.priority = payload.priority
        existing.suppression_window_seconds = payload.suppression_window_seconds
        existing.active_hours = active_hours_data
        existing.updated_at = utcnow()
        db.commit()
        return schemas.RouteUpsertResponse(id=existing.id, created=False)

    route = Route(
        id=payload.id,
        conditions=conditions_data,
        target=target_data,
        priority=payload.priority,
        suppression_window_seconds=payload.suppression_window_seconds,
        active_hours=active_hours_data,
    )
    db.add(route)
    db.commit()
    return schemas.RouteUpsertResponse(id=route.id, created=True)


@router.get("/routes", response_model=list[schemas.RouteResponse])
def list_routes(db: Session = Depends(get_db)):
    return db.query(Route).order_by(Route.id.asc()).all()


@router.delete("/routes/{route_id}", response_model=dict[str, str | bool], status_code=200)
def delete_route(route_id: str, db: Session = Depends(get_db)):
    route = db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail=f"Route '{route_id}' not found")
    db.delete(route)
    db.commit()
    return {"id": route_id, "deleted": True}
