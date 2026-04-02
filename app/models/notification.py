from sqlalchemy import Column, Integer, String, JSON, DateTime, Index

from app.database import Base, utcnow


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notification_alert_id", "alert_id"),
        Index("ix_notification_route_id", "route_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String, nullable=False)           # matches Alert.id
    route_id = Column(String, nullable=True)            # null when status = "unrouted"
    channel = Column(String, nullable=True)             # null when status = "unrouted"
    status = Column(String, nullable=False)             # pending | suppressed | unrouted

    # Routing snapshot — stored so GET /alerts/{id} can reconstruct the full response
    # without re-evaluating (routes may have changed since the alert was processed)
    routed_to = Column(JSON, nullable=True)             # {route_id, target} or null
    matched_route_ids = Column(JSON, nullable=False)    # list of all matched route IDs
    total_routes_evaluated = Column(Integer, nullable=False)
    suppression_reason = Column(String, nullable=True)  # only set when status = "suppressed"

    created_at = Column(DateTime, default=utcnow)
