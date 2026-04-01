from sqlalchemy import Column, Integer, String, JSON, DateTime

from app.database import Base, utcnow


class Route(Base):
    __tablename__ = "routes"

    id = Column(String, primary_key=True)                        # client-provided
    conditions = Column(JSON, nullable=False)                    # {severity?, service?, group?, labels?} — ALL fields must match
    target = Column(JSON, nullable=False)                        # {type: slack|email|pagerduty|webhook, ...type-specific fields}
    priority = Column(Integer, nullable=False)                   # higher = higher priority; highest match wins
    suppression_window_seconds = Column(Integer, default=0)      # 0 = no suppression
    active_hours = Column(JSON, nullable=True)                   # {timezone, start, end} — uses alert.timestamp for check
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
