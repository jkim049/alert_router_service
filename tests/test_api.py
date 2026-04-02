"""
API contract and validation tests.

These verify response shapes, status codes, error formats,
and the behaviour of endpoints outside the core routing flow.
"""

from tests.conftest import alert_payload, route_payload


# --- GET /health ---

def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# --- POST /routes ---

def test_create_route_returns_created_true(client):
    r = client.post("/routes", json=route_payload())
    assert r.status_code == 200
    assert r.json() == {"id": "route-1", "created": True}


def test_upsert_existing_route_returns_created_false(client):
    client.post("/routes", json=route_payload())
    r = client.post("/routes", json=route_payload(priority=99))
    assert r.status_code == 200
    assert r.json() == {"id": "route-1", "created": False}


def test_upsert_updates_route_fields(client):
    client.post("/routes", json=route_payload(priority=10))
    client.post("/routes", json=route_payload(priority=99))

    routes = client.get("/routes").json()
    assert routes[0]["priority"] == 99


# --- GET /routes ---

def test_get_routes_returns_empty_list_initially(client):
    assert client.get("/routes").json() == []


def test_get_routes_ordered_by_id_ascending(client):
    for rid in ["route-c", "route-a", "route-b"]:
        client.post("/routes", json=route_payload(id=rid))

    ids = [r["id"] for r in client.get("/routes").json()]
    assert ids == sorted(ids)


# --- DELETE /routes ---

def test_delete_route_removes_it_from_list(client):
    client.post("/routes", json=route_payload())
    client.delete("/routes/route-1")
    assert client.get("/routes").json() == []


def test_delete_route_returns_correct_response_shape(client):
    client.post("/routes", json=route_payload())
    r = client.delete("/routes/route-1")
    assert r.status_code == 200
    assert r.json() == {"id": "route-1", "deleted": True}


def test_delete_route_clears_suppression_records(client):
    """Deleting a route must clear its suppression records so a recreated route starts fresh."""
    client.post("/routes", json=route_payload(suppression_window_seconds=300))
    client.post("/alerts", json=alert_payload(id="a1"))  # sets suppression

    client.delete("/routes/route-1")
    client.post("/routes", json=route_payload(suppression_window_seconds=300))

    r = client.post("/alerts", json=alert_payload(id="a2")).json()
    assert r["suppressed"] is False


def test_delete_nonexistent_route_returns_404(client):
    r = client.delete("/routes/does-not-exist")
    assert r.status_code == 404


# --- GET /alerts/{id} ---

def test_get_alert_by_id_matches_post_response(client):
    """GET /alerts/{id} must return the same structure as the POST /alerts response."""
    client.post("/routes", json=route_payload())
    post_data = client.post("/alerts", json=alert_payload()).json()
    get_data = client.get("/alerts/alert-1").json()

    assert get_data == post_data


def test_get_alert_not_found_returns_correct_error(client):
    r = client.get("/alerts/nonexistent")
    assert r.status_code == 404
    assert r.json() == {"error": "alert not found"}


def test_get_alert_reflects_latest_submission(client):
    """After re-submission, GET returns the result of the most recent routing evaluation."""
    # First submission — unrouted
    client.post("/alerts", json=alert_payload(severity="warning"))
    assert client.get("/alerts/alert-1").json()["routed_to"] is None

    # Add matching route and re-submit
    client.post("/routes", json=route_payload(conditions={"severity": ["critical"]}))
    client.post("/alerts", json=alert_payload(severity="critical"))
    assert client.get("/alerts/alert-1").json()["routed_to"] is not None


# --- GET /alerts (filtered list) ---

def test_list_alerts_returns_empty_initially(client):
    r = client.get("/alerts").json()
    assert r == {"alerts": [], "total": 0}


def test_list_alerts_returns_all_when_no_filters(client):
    client.post("/routes", json=route_payload(conditions={}))
    client.post("/alerts", json=alert_payload(id="a1"))
    client.post("/alerts", json=alert_payload(id="a2"))

    r = client.get("/alerts").json()
    assert r["total"] == 2
    assert len(r["alerts"]) == 2


def test_list_alerts_filter_by_service(client):
    client.post("/routes", json=route_payload(conditions={}))
    client.post("/alerts", json=alert_payload(id="a1", service="payment-api"))
    client.post("/alerts", json=alert_payload(id="a2", service="auth-service"))

    r = client.get("/alerts?service=payment-api").json()
    assert r["total"] == 1
    assert r["alerts"][0]["alert_id"] == "a1"


def test_list_alerts_filter_by_severity(client):
    client.post("/routes", json=route_payload(conditions={}))
    client.post("/alerts", json=alert_payload(id="a1", severity="critical"))
    client.post("/alerts", json=alert_payload(id="a2", severity="warning"))

    r = client.get("/alerts?severity=critical").json()
    assert r["total"] == 1
    assert r["alerts"][0]["alert_id"] == "a1"


def test_list_alerts_filter_routed_true(client):
    client.post("/routes", json=route_payload(conditions={"severity": ["critical"]}))
    client.post("/alerts", json=alert_payload(id="a1", severity="critical"))  # routed
    client.post("/alerts", json=alert_payload(id="a2", severity="warning"))   # unrouted

    r = client.get("/alerts?routed=true").json()
    assert r["total"] == 1
    assert r["alerts"][0]["alert_id"] == "a1"


def test_list_alerts_filter_routed_true_includes_suppressed(client):
    """routed=true includes suppressed alerts — they matched a route, just weren't delivered."""
    client.post("/routes", json=route_payload(
        conditions={"severity": ["critical"]},
        suppression_window_seconds=300,
    ))
    client.post("/alerts", json=alert_payload(id="a1", severity="critical"))  # pending
    client.post("/alerts", json=alert_payload(id="a2", severity="critical"))  # suppressed
    client.post("/alerts", json=alert_payload(id="a3", severity="warning"))   # unrouted

    r = client.get("/alerts?routed=true").json()
    assert r["total"] == 2
    alert_ids = {a["alert_id"] for a in r["alerts"]}
    assert alert_ids == {"a1", "a2"}


def test_list_alerts_filter_routed_false_returns_only_unrouted(client):
    """routed=false returns only alerts that matched no route at all."""
    client.post("/routes", json=route_payload(
        conditions={"severity": ["critical"]},
        suppression_window_seconds=300,
    ))
    client.post("/alerts", json=alert_payload(id="a1", severity="critical"))  # pending
    client.post("/alerts", json=alert_payload(id="a2", severity="critical"))  # suppressed
    client.post("/alerts", json=alert_payload(id="a3", severity="warning"))   # unrouted

    r = client.get("/alerts?routed=false").json()
    assert r["total"] == 1
    assert r["alerts"][0]["alert_id"] == "a3"


def test_list_alerts_filter_suppressed_true(client):
    client.post("/routes", json=route_payload(suppression_window_seconds=300))
    client.post("/alerts", json=alert_payload(id="a1"))   # routed
    client.post("/alerts", json=alert_payload(id="a2"))   # suppressed

    r = client.get("/alerts?suppressed=true").json()
    assert r["total"] == 1
    assert r["alerts"][0]["alert_id"] == "a2"


# --- POST /test (dry run) ---

def test_test_endpoint_returns_same_structure_as_post_alerts(client):
    client.post("/routes", json=route_payload())
    r = client.post("/test", json=alert_payload())

    assert r.status_code == 200
    data = r.json()
    assert "alert_id" in data
    assert "routed_to" in data
    assert "matched_routes" in data
    assert "evaluation_details" in data


def test_test_endpoint_produces_no_side_effects(client):
    """Dry-run must not create notifications, update suppression, or appear in stats."""
    client.post("/routes", json=route_payload(suppression_window_seconds=300))

    # Dry-run — should show routed but not set suppression
    test_result = client.post("/test", json=alert_payload()).json()
    assert test_result["suppressed"] is False

    # Real submission — should NOT be suppressed (dry-run didn't consume the window)
    real_result = client.post("/alerts", json=alert_payload()).json()
    assert real_result["suppressed"] is False

    # Stats should reflect only the one real submission
    stats = client.get("/stats").json()
    assert stats["total_alerts_processed"] == 1


# --- POST /seed ---

def test_seed_returns_seeded_true_on_first_call(client):
    r = client.post("/seed")
    assert r.status_code == 200
    assert r.json() == {"seeded": True}


def test_seed_returns_seeded_false_when_data_exists(client):
    client.post("/seed")
    r = client.post("/seed")
    assert r.status_code == 200
    assert r.json() == {"seeded": False}


def test_seed_populates_routes_and_alerts(client):
    client.post("/seed")
    routes = client.get("/routes").json()
    stats = client.get("/stats").json()
    assert len(routes) > 0
    assert stats["total_alerts_processed"] > 0


# --- POST /reset ---

def test_reset_clears_all_routes_and_alerts(client):
    client.post("/routes", json=route_payload())
    client.post("/alerts", json=alert_payload())

    r = client.post("/reset")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert client.get("/routes").json() == []
    assert client.get("/stats").json()["total_alerts_processed"] == 0


def test_reset_clears_suppression_state(client):
    """After reset, a previously suppressed service should route again."""
    client.post("/routes", json=route_payload(suppression_window_seconds=300))
    client.post("/alerts", json=alert_payload(id="a1"))  # sets suppression
    client.post("/reset")

    # Recreate the route and re-submit — should NOT be suppressed
    client.post("/routes", json=route_payload(suppression_window_seconds=300))
    r = client.post("/alerts", json=alert_payload(id="a2")).json()
    assert r["suppressed"] is False


# --- GET /stats ---

def test_stats_total_alerts_processed_counts_resubmissions(client):
    """Re-submitting the same alert ID counts as a separate processing event in total_alerts_processed."""
    client.post("/routes", json=route_payload(conditions={}))
    client.post("/alerts", json=alert_payload(id="a1"))
    client.post("/alerts", json=alert_payload(id="a1"))  # re-submission
    client.post("/alerts", json=alert_payload(id="a2"))

    stats = client.get("/stats").json()
    assert stats["total_alerts_processed"] == 3


def test_stats_are_zero_on_empty_state(client):
    stats = client.get("/stats").json()
    assert stats["total_alerts_processed"] == 0
    assert stats["total_routed"] == 0
    assert stats["total_suppressed"] == 0
    assert stats["total_unrouted"] == 0


def test_stats_counts_all_three_statuses(client):
    client.post("/routes", json=route_payload(
        conditions={"severity": ["critical"]},
        suppression_window_seconds=300,
    ))
    client.post("/alerts", json=alert_payload(id="a1", severity="critical"))  # routed
    client.post("/alerts", json=alert_payload(id="a2", severity="critical"))  # suppressed
    client.post("/alerts", json=alert_payload(id="a3", severity="warning"))   # unrouted

    stats = client.get("/stats").json()
    assert stats["total_alerts_processed"] == 3
    assert stats["total_routed"] == 1
    assert stats["total_suppressed"] == 1
    assert stats["total_unrouted"] == 1


def test_stats_by_severity_counts_per_severity(client):
    client.post("/routes", json=route_payload(conditions={}))
    client.post("/alerts", json=alert_payload(id="a1", severity="critical"))
    client.post("/alerts", json=alert_payload(id="a2", severity="critical"))
    client.post("/alerts", json=alert_payload(id="a3", severity="warning"))

    by_severity = client.get("/stats").json()["by_severity"]
    assert by_severity["critical"] == 2
    assert by_severity["warning"] == 1
    assert "info" not in by_severity


def test_stats_by_service_counts_per_service(client):
    client.post("/routes", json=route_payload(conditions={}))
    client.post("/alerts", json=alert_payload(id="a1", service="payment-api"))
    client.post("/alerts", json=alert_payload(id="a2", service="payment-api"))
    client.post("/alerts", json=alert_payload(id="a3", service="auth-service"))

    by_service = client.get("/stats").json()["by_service"]
    assert by_service["payment-api"] == 2
    assert by_service["auth-service"] == 1


def test_stats_by_route_reflects_matched_and_suppressed(client):
    client.post("/routes", json=route_payload(suppression_window_seconds=300))
    client.post("/alerts", json=alert_payload(id="a1"))  # routed
    client.post("/alerts", json=alert_payload(id="a2"))  # suppressed

    route_stats = client.get("/stats").json()["by_route"]["route-1"]
    assert route_stats["total_routed"] == 1
    assert route_stats["total_suppressed"] == 1
    assert route_stats["total_matched"] == 2


# --- Schema unit tests ---

def test_from_notification_handles_null_matched_route_ids():
    """from_notification must not crash when matched_route_ids is None (corrupted/legacy record)."""
    from app.models.notification import Notification
    from app.schemas.alerts import AlertIngestResponse

    notif = Notification(
        alert_id="alert-1",
        status="pending",
        routed_to=None,
        matched_route_ids=None,
        total_routes_evaluated=0,
        suppression_reason=None,
    )
    result = AlertIngestResponse.from_notification(notif)
    assert result.matched_routes == []
    assert result.evaluation_details.routes_matched == 0


# --- Validation (400 errors with {"error": "..."} body) ---

def test_missing_required_alert_field_returns_400(client):
    payload = alert_payload()
    del payload["severity"]
    r = client.post("/alerts", json=payload)
    assert r.status_code == 400
    assert "error" in r.json()


def test_invalid_severity_value_returns_400(client):
    r = client.post("/alerts", json=alert_payload(severity="extreme"))
    assert r.status_code == 400
    assert "error" in r.json()


def test_invalid_target_type_returns_400(client):
    r = client.post("/routes", json=route_payload(target={"type": "telegram", "chat_id": "123"}))
    assert r.status_code == 400
    assert "error" in r.json()


def test_negative_suppression_window_returns_400(client):
    r = client.post("/routes", json=route_payload(suppression_window_seconds=-60))
    assert r.status_code == 400
    assert "error" in r.json()


def test_invalid_iana_timezone_returns_400(client):
    r = client.post("/routes", json=route_payload(
        active_hours={"timezone": "Not/ATimezone", "start": "09:00", "end": "17:00"},
    ))
    assert r.status_code == 400
    assert "error" in r.json()


def test_invalid_time_format_returns_400(client):
    r = client.post("/routes", json=route_payload(
        active_hours={"timezone": "UTC", "start": "9:00", "end": "17:00"},  # missing leading zero
    ))
    assert r.status_code == 400
    assert "error" in r.json()


def test_invalid_timestamp_returns_400(client):
    r = client.post("/alerts", json=alert_payload(timestamp="25-03-2026"))
    assert r.status_code == 400
    assert "error" in r.json()


def test_missing_required_route_field_returns_400(client):
    payload = route_payload()
    del payload["priority"]
    r = client.post("/routes", json=payload)
    assert r.status_code == 400
    assert "error" in r.json()
