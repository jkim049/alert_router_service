from sqlalchemy import Column, String, JSON, DateTime

from app.database import Base, utcnow


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String, primary_key=True)           # client-provided, used as upsert key
    severity = Column(String, nullable=False)        # critical | warning | info
    service = Column(String, nullable=False)
    group = Column(String, nullable=False)
    description = Column(String, default="")
    timestamp = Column(DateTime, nullable=False)     # client-provided ISO 8601
    labels = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
