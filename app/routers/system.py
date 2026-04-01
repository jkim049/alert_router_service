from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert, Route, SuppressionRecord, Notification
from app.seed import seed_db

router = APIRouter()


@router.get("/health", response_model=dict[str, str], tags=["Health"])
def health():
    return {"status": "ok"}


@router.post("/seed", response_model=dict[str, bool], status_code=200, tags=["Seed"])
def seed(db: Session = Depends(get_db)):
    """Insert sample routes and alerts. Has no effect if data already exists."""
    seeded = seed_db(db)
    return {"seeded": seeded}


@router.post("/reset", response_model=dict[str, str], status_code=200, tags=["Reset"])
def reset(db: Session = Depends(get_db)):
    """Clear all routes, alerts, notifications, and suppression records."""
    db.query(Notification).delete()
    db.query(SuppressionRecord).delete()
    db.query(Alert).delete()
    db.query(Route).delete()
    db.commit()
    return {"status": "ok"}
