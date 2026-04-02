from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint

from app.database import Base


class SuppressionRecord(Base):
    """Tracks when a (route, service) pair last fired, for suppression window enforcement."""
    __tablename__ = "suppression_records"
    __table_args__ = (UniqueConstraint("route_id", "service", name="uq_suppression_route_service"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    route_id = Column(String, nullable=False)
    service = Column(String, nullable=False)
    suppressed_until = Column(DateTime, nullable=False)
