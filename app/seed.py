"""
Seed script — inserts sample data into an empty database.

Called via POST /seed. Safe to call repeatedly:
exits immediately if any routes already exist.

Seed routes cover the four target types and common real-world patterns:
  - route-critical-pagerduty  Critical alerts → PagerDuty (priority 100, 5-min suppression)
  - route-payment-slack       Payment service alerts → Slack #payments-oncall (priority 50)
  - route-infra-email         Infrastructure group → email ops@example.com (priority 30)
  - route-warnings-webhook    Warning alerts, business hours only → webhook (priority 10)

Seed alerts show all three routing outcomes (pending, suppressed, unrouted).
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.constants import NOTIFICATION_PENDING, NOTIFICATION_UNROUTED
from app.database import utcnow
from app.models import Alert, Route, Notification, SuppressionRecord


def seed_db(db: Session) -> bool:
    """Insert sample data. Returns True if data was inserted, False if the database was already populated."""
    if db.query(Route).count() > 0:
        return False

    # --- Routes ---

    routes = [
        Route(
            id="route-critical-pagerduty",
            conditions={"severity": ["critical"]},
            target={"type": "pagerduty", "service_key": "pd-integration-key-demo"},
            priority=100,
            suppression_window_seconds=300,
        ),
        Route(
            id="route-payment-slack",
            conditions={"service": ["payment-*"]},
            target={"type": "slack", "channel": "#payments-oncall"},
            priority=50,
            suppression_window_seconds=60,
        ),
        Route(
            id="route-infra-email",
            conditions={"group": ["infrastructure"]},
            target={"type": "email", "address": "ops@example.com"},
            priority=30,
            suppression_window_seconds=0,
        ),
        Route(
            id="route-warnings-webhook",
            conditions={"severity": ["warning"]},
            target={
                "type": "webhook",
                "url": "https://hooks.example.com/alerts",
                "headers": {"Authorization": "Bearer demo-token"},
            },
            priority=10,
            suppression_window_seconds=0,
            active_hours={"timezone": "UTC", "start": "09:00", "end": "17:00"},
        ),
    ]
    db.add_all(routes)
    db.flush()

    # --- Alerts and their notification records ---

    now = utcnow()

    # alert-001: critical payment alert — routes to PagerDuty (pending)
    alert1 = Alert(
        id="alert-001",
        severity="critical",
        service="payment-api",
        group="backend",
        description="Payment processing latency exceeded 2s threshold",
        timestamp=datetime(2026, 3, 25, 14, 30, 0),
        labels={"env": "prod", "region": "us-east-1"},
    )
    db.add(alert1)
    db.flush()
    db.add(Notification(
        alert_id="alert-001",
        route_id="route-critical-pagerduty",
        channel="pagerduty",
        status=NOTIFICATION_PENDING,
        routed_to={"route_id": "route-critical-pagerduty", "target": {"type": "pagerduty", "service_key": "pd-integration-key-demo"}},
        matched_route_ids=["route-critical-pagerduty", "route-payment-slack"],
        total_routes_evaluated=4,
        suppression_reason=None,
    ))
    # Set a suppression record so the second payment alert is suppressed
    db.add(SuppressionRecord(
        route_id="route-critical-pagerduty",
        service="payment-api",
        suppressed_until=now.replace(year=now.year + 10),  # far future — always suppressed in demo
    ))

    # alert-002: second critical payment alert — suppressed by route-critical-pagerduty,
    # falls through to route-payment-slack (pending)
    alert2 = Alert(
        id="alert-002",
        severity="critical",
        service="payment-api",
        group="backend",
        description="Payment processing latency still elevated",
        timestamp=datetime(2026, 3, 25, 14, 32, 0),
        labels={"env": "prod", "region": "us-east-1"},
    )
    db.add(alert2)
    db.flush()
    db.add(Notification(
        alert_id="alert-002",
        route_id="route-payment-slack",
        channel="slack",
        status=NOTIFICATION_PENDING,
        routed_to={"route_id": "route-payment-slack", "target": {"type": "slack", "channel": "#payments-oncall"}},
        matched_route_ids=["route-critical-pagerduty", "route-payment-slack"],
        total_routes_evaluated=4,
        suppression_reason=None,
    ))

    # alert-003: infrastructure warning — routes to route-infra-email (pending)
    alert3 = Alert(
        id="alert-003",
        severity="warning",
        service="db-primary",
        group="infrastructure",
        description="Disk usage above 80% on primary database host",
        timestamp=datetime(2026, 3, 25, 15, 0, 0),
        labels={"env": "prod", "host": "db-01"},
    )
    db.add(alert3)
    db.flush()
    db.add(Notification(
        alert_id="alert-003",
        route_id="route-infra-email",
        channel="email",
        status=NOTIFICATION_PENDING,
        routed_to={"route_id": "route-infra-email", "target": {"type": "email", "address": "ops@example.com"}},
        matched_route_ids=["route-infra-email"],
        total_routes_evaluated=4,
        suppression_reason=None,
    ))

    # alert-004: info alert — no matching route (unrouted)
    alert4 = Alert(
        id="alert-004",
        severity="info",
        service="auth-service",
        group="backend",
        description="Scheduled certificate renewal completed successfully",
        timestamp=datetime(2026, 3, 25, 16, 0, 0),
        labels={"env": "prod"},
    )
    db.add(alert4)
    db.flush()
    db.add(Notification(
        alert_id="alert-004",
        route_id=None,
        channel=None,
        status=NOTIFICATION_UNROUTED,
        routed_to=None,
        matched_route_ids=[],
        total_routes_evaluated=4,
        suppression_reason=None,
    ))

    db.commit()
    return True
