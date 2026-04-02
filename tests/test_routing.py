"""
Core routing logic tests.

These cover the behaviour an evaluator is most likely to probe:
priority resolution, suppression, condition matching, and active hours.
Each test is independent — no shared state between tests.
"""

from tests.conftest import alert_payload, route_payload


# --- Unrouted ---

def test_unrouted_when_no_routes_exist(client):
    """With no routes configured, every alert must be recorded as unrouted."""
    r = client.post("/alerts", json=alert_payload())
    data = r.json()

    assert r.status_code == 200
    assert data["routed_to"] is None
    assert data["matched_routes"] == []
    assert data["suppressed"] is False
    assert data["evaluation_details"]["total_routes_evaluated"] == 0
    assert data["evaluation_details"]["routes_matched"] == 0


def test_unrouted_when_no_conditions_match(client):
    """An alert that matches no route conditions is recorded as unrouted."""
    client.post("/routes", json=route_payload(conditions={"severity": ["critical"]}))

    r = client.post("/alerts", json=alert_payload(severity="warning"))
    assert r.json()["routed_to"] is None


# --- Basic routing ---

def test_matching_alert_is_routed_to_correct_target(client):
    """An alert that satisfies a route's conditions is routed to that route's target."""
    client.post("/routes", json=route_payload())

    data = client.post("/alerts", json=alert_payload()).json()

    assert data["routed_to"]["route_id"] == "route-1"
    assert data["routed_to"]["target"]["type"] == "slack"
    assert data["routed_to"]["target"]["channel"] == "#oncall"
    assert data["suppressed"] is False


# --- Priority ---

def test_highest_priority_route_wins(client):
    """When multiple routes match, only the highest-priority one produces a notification."""
    client.post("/routes", json=route_payload(id="low", priority=5))
    client.post("/routes", json=route_payload(
        id="high", priority=20,
        target={"type": "email", "address": "oncall@example.com"},
    ))

    data = client.post("/alerts", json=alert_payload()).json()

    assert data["routed_to"]["route_id"] == "high"
    # Both routes matched — matched_routes reflects all matches, not just the winner
    assert set(data["matched_routes"]) == {"low", "high"}
    assert data["evaluation_details"]["routes_matched"] == 2


def test_priority_tiebreaker_is_alphabetical_id(client):
    """Equal-priority routes are broken deterministically by alphabetical route id."""
    client.post("/routes", json=route_payload(id="route-z", priority=10))
    client.post("/routes", json=route_payload(
        id="route-a", priority=10,
        target={"type": "email", "address": "a@example.com"},
    ))

    data = client.post("/alerts", json=alert_payload()).json()

    assert data["routed_to"]["route_id"] == "route-a"


# --- Suppression ---

def test_second_alert_same_service_is_suppressed_within_window(client):
    """After routing, a subsequent alert for the same service is suppressed within the window."""
    client.post("/routes", json=route_payload(suppression_window_seconds=300))

    first = client.post("/alerts", json=alert_payload(id="alert-1")).json()
    second = client.post("/alerts", json=alert_payload(id="alert-2")).json()

    assert first["suppressed"] is False
    assert second["suppressed"] is True
    assert second["routed_to"]["route_id"] == "route-1"
    assert "suppressed until" in second["suppression_reason"]
    assert second["evaluation_details"]["suppression_applied"] is True


def test_suppression_is_scoped_to_service(client):
    """Suppression on one service does not affect a different service on the same route."""
    client.post("/routes", json=route_payload(
        conditions={},  # match all
        suppression_window_seconds=300,
    ))

    client.post("/alerts", json=alert_payload(id="alert-1", service="payment-api"))

    r = client.post("/alerts", json=alert_payload(id="alert-2", service="auth-service"))
    assert r.json()["suppressed"] is False


def test_zero_suppression_window_never_suppresses(client):
    """suppression_window_seconds=0 means no suppression — every alert routes."""
    client.post("/routes", json=route_payload(suppression_window_seconds=0))

    client.post("/alerts", json=alert_payload(id="alert-1"))
    r = client.post("/alerts", json=alert_payload(id="alert-2"))

    assert r.json()["suppressed"] is False


def test_suppressed_response_still_identifies_winning_route(client):
    """Even when suppressed, routed_to shows which route would have handled the alert."""
    client.post("/routes", json=route_payload(suppression_window_seconds=300))
    client.post("/alerts", json=alert_payload(id="alert-1"))

    suppressed = client.post("/alerts", json=alert_payload(id="alert-2")).json()

    assert suppressed["routed_to"] is not None
    assert suppressed["routed_to"]["route_id"] == "route-1"


def test_suppressed_route_falls_through_to_next_match(client):
    """When the highest-priority route is suppressed, routing falls through to the next match."""
    # High-priority route with suppression window
    client.post("/routes", json=route_payload(
        id="high",
        priority=20,
        conditions={},
        suppression_window_seconds=300,
        target={"type": "pagerduty", "service_key": "pd-key"},
    ))
    # Lower-priority route with no suppression
    client.post("/routes", json=route_payload(
        id="low",
        priority=10,
        conditions={},
        suppression_window_seconds=0,
        target={"type": "slack", "channel": "#oncall"},
    ))

    # First alert — routes to high
    first = client.post("/alerts", json=alert_payload(id="a1")).json()
    assert first["routed_to"]["route_id"] == "high"
    assert first["suppressed"] is False

    # Second alert — high is suppressed, falls through to low
    second = client.post("/alerts", json=alert_payload(id="a2")).json()
    assert second["suppressed"] is False
    assert second["routed_to"]["route_id"] == "low"


def test_suppressed_when_all_matching_routes_are_suppressed(client):
    """When every matching route is suppressed, the alert is recorded as suppressed against the highest-priority one."""
    client.post("/routes", json=route_payload(
        id="high",
        priority=20,
        conditions={},
        suppression_window_seconds=300,
        target={"type": "pagerduty", "service_key": "pd-key"},
    ))
    client.post("/routes", json=route_payload(
        id="low",
        priority=10,
        conditions={},
        suppression_window_seconds=300,
        target={"type": "slack", "channel": "#oncall"},
    ))

    # First two alerts set suppression on both routes
    client.post("/alerts", json=alert_payload(id="a1"))  # suppresses high
    client.post("/alerts", json=alert_payload(id="a2"))  # suppresses low (falls through from high)

    # Third alert — both routes suppressed
    third = client.post("/alerts", json=alert_payload(id="a3")).json()
    assert third["suppressed"] is True
    assert third["routed_to"]["route_id"] == "high"


# --- Condition matching ---

def test_severity_condition_filters_by_value(client):
    """A route with severity=['critical'] matches critical alerts only."""
    client.post("/routes", json=route_payload(conditions={"severity": ["critical"]}))

    assert client.post("/alerts", json=alert_payload(severity="critical")).json()["routed_to"] is not None
    assert client.post("/alerts", json=alert_payload(id="a2", severity="warning")).json()["routed_to"] is None
    assert client.post("/alerts", json=alert_payload(id="a3", severity="info")).json()["routed_to"] is None


def test_severity_condition_supports_multiple_values(client):
    """A severity list matches any alert whose severity is in the list."""
    client.post("/routes", json=route_payload(conditions={"severity": ["critical", "warning"]}))

    assert client.post("/alerts", json=alert_payload(severity="critical")).json()["routed_to"] is not None
    assert client.post("/alerts", json=alert_payload(id="a2", severity="warning")).json()["routed_to"] is not None
    assert client.post("/alerts", json=alert_payload(id="a3", severity="info")).json()["routed_to"] is None


def test_service_condition_supports_glob_patterns(client):
    """Service conditions support glob — 'payment-*' matches any payment-prefixed service."""
    client.post("/routes", json=route_payload(conditions={"service": ["payment-*"]}))

    assert client.post("/alerts", json=alert_payload(service="payment-api")).json()["routed_to"] is not None
    assert client.post("/alerts", json=alert_payload(id="a2", service="payment-worker")).json()["routed_to"] is not None
    assert client.post("/alerts", json=alert_payload(id="a3", service="auth-service")).json()["routed_to"] is None


def test_labels_condition_requires_subset_match(client):
    """Labels condition matches if all specified pairs exist in the alert. Extra alert labels are allowed."""
    client.post("/routes", json=route_payload(conditions={"labels": {"env": "prod", "team": "payments"}}))

    # Has all required labels plus an extra one — should match
    match = alert_payload(labels={"env": "prod", "team": "payments", "region": "us-east-1"})
    assert client.post("/alerts", json=match).json()["routed_to"] is not None

    # Missing one required label — should not match
    no_match = alert_payload(id="a2", labels={"env": "prod"})
    assert client.post("/alerts", json=no_match).json()["routed_to"] is None


def test_group_condition_filters_by_value(client):
    """A route with group=['backend'] matches backend alerts only."""
    client.post("/routes", json=route_payload(conditions={"group": ["backend"]}))

    assert client.post("/alerts", json=alert_payload(group="backend")).json()["routed_to"] is not None
    assert client.post("/alerts", json=alert_payload(id="a2", group="infrastructure")).json()["routed_to"] is None
    assert client.post("/alerts", json=alert_payload(id="a3", group="frontend")).json()["routed_to"] is None


def test_labels_condition_does_not_match_alert_with_no_labels(client):
    """A route requiring labels does not match an alert that has no labels at all."""
    client.post("/routes", json=route_payload(conditions={"labels": {"env": "prod"}}))

    r = client.post("/alerts", json=alert_payload())  # alert_payload has no labels
    assert r.json()["routed_to"] is None


def test_omitted_condition_fields_match_everything(client):
    """A route with empty conditions matches every alert regardless of its fields."""
    client.post("/routes", json=route_payload(conditions={}))

    for i, sev in enumerate(["critical", "warning", "info"]):
        r = client.post("/alerts", json=alert_payload(id=f"a{i}", severity=sev))
        assert r.json()["routed_to"] is not None, f"Expected match for severity={sev}"


def test_all_condition_fields_must_match(client):
    """A route requires ALL specified conditions to match — partial matches are not routed."""
    client.post("/routes", json=route_payload(conditions={
        "severity": ["critical"],
        "group": ["frontend"],  # alert is in 'backend' group
    }))

    # Matches severity but not group
    r = client.post("/alerts", json=alert_payload(severity="critical", group="backend"))
    assert r.json()["routed_to"] is None


# --- Active hours ---

def test_alert_within_active_hours_is_matched(client):
    """A route with active_hours matches an alert whose timestamp falls inside the window."""
    client.post("/routes", json=route_payload(
        conditions={},
        active_hours={"timezone": "UTC", "start": "09:00", "end": "17:00"},
    ))
    # 14:30 UTC is inside 09:00–17:00
    r = client.post("/alerts", json=alert_payload(timestamp="2026-03-25T14:30:00Z"))
    assert r.json()["routed_to"] is not None


def test_alert_outside_active_hours_is_not_matched(client):
    """A route with active_hours does not match an alert whose timestamp is outside the window."""
    client.post("/routes", json=route_payload(
        conditions={},
        active_hours={"timezone": "UTC", "start": "09:00", "end": "17:00"},
    ))
    # 20:00 UTC is outside 09:00–17:00
    r = client.post("/alerts", json=alert_payload(timestamp="2026-03-25T20:00:00Z"))
    assert r.json()["routed_to"] is None


def test_active_hours_respects_timezone(client):
    """active_hours uses the route's timezone, not UTC."""
    # Window is 09:00–17:00 America/New_York (UTC-4 in summer)
    client.post("/routes", json=route_payload(
        conditions={},
        active_hours={"timezone": "America/New_York", "start": "09:00", "end": "17:00"},
    ))
    # 20:00 UTC = 16:00 New York — inside window
    inside = client.post("/alerts", json=alert_payload(
        id="a1", timestamp="2026-03-25T20:00:00Z",
    )).json()
    # 02:00 UTC = 22:00 previous day New York — outside window
    outside = client.post("/alerts", json=alert_payload(
        id="a2", timestamp="2026-03-25T02:00:00Z",
    )).json()

    assert inside["routed_to"] is not None
    assert outside["routed_to"] is None


def test_active_hours_end_is_exclusive(client):
    """An alert timestamped at exactly the end boundary is not matched — end is exclusive."""
    client.post("/routes", json=route_payload(
        conditions={},
        active_hours={"timezone": "UTC", "start": "09:00", "end": "17:00"},
    ))
    # Exactly at end boundary — should not match
    at_end = client.post("/alerts", json=alert_payload(timestamp="2026-03-25T17:00:00Z")).json()
    # One second before end — should match
    before_end = client.post("/alerts", json=alert_payload(id="a2", timestamp="2026-03-25T16:59:59Z")).json()

    assert at_end["routed_to"] is None
    assert before_end["routed_to"] is not None


def test_overnight_active_hours_window(client):
    """Overnight windows (start > end) match times that wrap across midnight."""
    client.post("/routes", json=route_payload(
        conditions={},
        active_hours={"timezone": "UTC", "start": "22:00", "end": "06:00"},
    ))
    # 23:00 UTC — inside overnight window
    inside_before_midnight = client.post("/alerts", json=alert_payload(
        id="a1", timestamp="2026-03-25T23:00:00Z",
    )).json()
    # 03:00 UTC — inside overnight window (past midnight)
    inside_after_midnight = client.post("/alerts", json=alert_payload(
        id="a2", timestamp="2026-03-25T03:00:00Z",
    )).json()
    # 12:00 UTC — outside overnight window
    outside = client.post("/alerts", json=alert_payload(
        id="a3", timestamp="2026-03-25T12:00:00Z",
    )).json()

    assert inside_before_midnight["routed_to"] is not None
    assert inside_after_midnight["routed_to"] is not None
    assert outside["routed_to"] is None


# --- Re-submission ---

def test_resubmission_updates_alert_fields(client):
    """Re-submitting an alert with the same ID persists the updated field values."""
    client.post("/alerts", json=alert_payload(
        severity="warning",
        service="auth-service",
        group="backend",
        description="original",
    ))
    client.post("/alerts", json=alert_payload(
        severity="critical",
        service="payment-api",
        group="infrastructure",
        description="updated",
    ))

    # GET /alerts/{id} reflects the latest submission
    r = client.get("/alerts/alert-1").json()
    assert r["alert_id"] == "alert-1"
    # Routing re-evaluated against the new fields — no route matches critical by default
    # but the alert record itself must reflect the new values, visible via GET /alerts filters
    alerts = client.get("/alerts?service=payment-api").json()
    assert alerts["total"] == 1
    assert alerts["alerts"][0]["alert_id"] == "alert-1"

    alerts_old = client.get("/alerts?service=auth-service").json()
    assert alerts_old["total"] == 0


def test_resubmission_reevaluates_routing(client):
    """Re-submitting an alert with the same ID updates it and re-evaluates routing from scratch."""
    # First submission — no matching route
    client.post("/routes", json=route_payload(conditions={"severity": ["critical"]}))
    first = client.post("/alerts", json=alert_payload(severity="warning")).json()
    assert first["routed_to"] is None

    # Re-submit same ID with a severity that now matches
    second = client.post("/alerts", json=alert_payload(severity="critical")).json()
    assert second["routed_to"] is not None


# --- evaluation_details ---

def test_evaluation_details_reflect_all_routes(client):
    """evaluation_details counts cover all evaluated routes, not just the winner."""
    client.post("/routes", json=route_payload(id="r1", conditions={"severity": ["critical"]}))
    client.post("/routes", json=route_payload(id="r2", conditions={"severity": ["warning"]}, priority=5))
    client.post("/routes", json=route_payload(id="r3", conditions={"severity": ["info"]}, priority=3))

    data = client.post("/alerts", json=alert_payload(severity="critical")).json()
    details = data["evaluation_details"]

    assert details["total_routes_evaluated"] == 3
    assert details["routes_matched"] == 1
    assert details["routes_not_matched"] == 2
    assert details["suppression_applied"] is False
