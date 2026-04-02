#!/usr/bin/env python3
"""
Section 8: Alert Re-submission
Covers:
  - Re-posting same alert ID updates the record
  - GET /alerts/{id} always returns latest routing result
  - Re-evaluation uses current routes (not routes at time of first submission)
  - Field values are updated on re-submission
  - Routing outcome can change between submissions
  - stats.total_alerts_processed counts each submission
  - Suppression state interacts correctly with re-submission
  - matched_routes reflects re-evaluation, not original
"""

import sys
import requests

BASE_URL = "http://localhost:8080"
passed = 0
failed = 0


def check(description, condition, actual=None):
    global passed, failed
    if condition:
        print(f"  PASS  {description}")
        passed += 1
    else:
        print(f"  FAIL  {description}" + (f"\n        got: {actual}" if actual is not None else ""))
        failed += 1


def reset():
    requests.post(f"{BASE_URL}/reset")


def section(title):
    print(f"\n--- {title} ---")


def post_route(id, conditions=None, priority=10, suppression_window_seconds=0):
    requests.post(f"{BASE_URL}/routes", json={
        "id": id,
        "conditions": conditions or {},
        "target": {"type": "slack", "channel": f"#{id}"},
        "priority": priority,
        "suppression_window_seconds": suppression_window_seconds,
    })


def post_alert(id="alert-1", severity="critical", service="payment-api",
               group="backend", timestamp="2026-03-25T14:30:00Z",
               description="", labels=None):
    payload = {
        "id": id, "severity": severity, "service": service,
        "group": group, "timestamp": timestamp, "description": description,
    }
    if labels:
        payload["labels"] = labels
    return requests.post(f"{BASE_URL}/alerts", json=payload).json()


def get_alert(id):
    return requests.get(f"{BASE_URL}/alerts/{id}").json()


# -------------------------------------------------------------------------
# Basic re-submission — GET returns latest result
# -------------------------------------------------------------------------
reset()
section("Basic re-submission — GET returns latest result")

post_route("route-critical", conditions={"severity": ["critical"]}, priority=10)

first = post_alert(id="alert-1", severity="warning")  # no match
check("First submission (no match): routed_to is null", first["routed_to"] is None, first.get("routed_to"))

second = post_alert(id="alert-1", severity="critical")  # now matches
check("Re-submission (now matches): routed_to is set", second["routed_to"] is not None, second.get("routed_to"))
check("Re-submission returns correct route", second["routed_to"]["route_id"] == "route-critical", second.get("routed_to"))

get = get_alert("alert-1")
check("GET /alerts/{id} reflects latest submission", get["routed_to"] is not None, get.get("routed_to"))
check("GET result matches POST response", get == second, {"get": get, "second": second})


# -------------------------------------------------------------------------
# Re-submission flips from routed to unrouted
# -------------------------------------------------------------------------
reset()
section("Re-submission: routed → unrouted")

post_route("route-critical", conditions={"severity": ["critical"]})

first = post_alert(id="alert-1", severity="critical")
check("First submission routes", first["routed_to"] is not None, first.get("routed_to"))

second = post_alert(id="alert-1", severity="info")  # no route matches info
check("Re-submission with non-matching severity: unrouted", second["routed_to"] is None, second.get("routed_to"))
check("Re-submission with non-matching severity: matched_routes empty", second["matched_routes"] == [], second.get("matched_routes"))

get = get_alert("alert-1")
check("GET reflects unrouted state after re-submission", get["routed_to"] is None, get.get("routed_to"))


# -------------------------------------------------------------------------
# Field values are updated on re-submission
# -------------------------------------------------------------------------
reset()
section("Field values updated on re-submission")

post_route("route-all", conditions={}, priority=10)

post_alert(
    id="alert-1",
    severity="warning",
    service="auth-service",
    group="frontend",
    timestamp="2026-01-01T10:00:00Z",
    description="original description",
    labels={"env": "staging"},
)

post_alert(
    id="alert-1",
    severity="critical",
    service="payment-api",
    group="backend",
    timestamp="2026-06-15T20:00:00Z",
    description="updated description",
    labels={"env": "prod", "region": "us-east-1"},
)

# Verify updated fields are reflected in list filters
r = requests.get(f"{BASE_URL}/alerts?service=payment-api").json()
check("Updated service visible via GET /alerts filter", r["total"] == 1, r)

r = requests.get(f"{BASE_URL}/alerts?service=auth-service").json()
check("Old service no longer matches filter", r["total"] == 0, r)

r = requests.get(f"{BASE_URL}/alerts?severity=critical").json()
check("Updated severity visible via GET /alerts filter", r["total"] == 1, r)

r = requests.get(f"{BASE_URL}/alerts?severity=warning").json()
check("Old severity no longer matches filter", r["total"] == 0, r)


# -------------------------------------------------------------------------
# Re-evaluation uses current routes
# -------------------------------------------------------------------------
reset()
section("Re-evaluation uses routes at time of re-submission")

# First submission — no routes exist
first = post_alert(id="alert-1", severity="critical")
check("First submission with no routes: unrouted", first["routed_to"] is None, first.get("routed_to"))
check("First submission: total_routes_evaluated = 0", first["evaluation_details"]["total_routes_evaluated"] == 0, first["evaluation_details"])

# Add route, re-submit same alert
post_route("route-critical", conditions={"severity": ["critical"]})
second = post_alert(id="alert-1", severity="critical")
check("Re-submission after route added: now routes", second["routed_to"] is not None, second.get("routed_to"))
check("Re-submission: total_routes_evaluated = 1", second["evaluation_details"]["total_routes_evaluated"] == 1, second["evaluation_details"])

# Delete route, re-submit
requests.delete(f"{BASE_URL}/routes/route-critical")
third = post_alert(id="alert-1", severity="critical")
check("Re-submission after route deleted: unrouted again", third["routed_to"] is None, third.get("routed_to"))
check("Re-submission: total_routes_evaluated = 0 again", third["evaluation_details"]["total_routes_evaluated"] == 0, third["evaluation_details"])


# -------------------------------------------------------------------------
# matched_routes reflects current evaluation
# -------------------------------------------------------------------------
reset()
section("matched_routes reflects current evaluation, not original")

post_route("route-a", conditions={"severity": ["critical"]}, priority=20)
post_route("route-b", conditions={"severity": ["critical", "warning"]}, priority=10)

first = post_alert(id="alert-1", severity="critical")
check("First: matched_routes includes both routes", set(first["matched_routes"]) == {"route-a", "route-b"}, first.get("matched_routes"))

second = post_alert(id="alert-1", severity="warning")
check("Re-submission: matched_routes reflects new severity match", second["matched_routes"] == ["route-b"], second.get("matched_routes"))
check("Re-submission: winner is route-b (only match)", second["routed_to"]["route_id"] == "route-b", second.get("routed_to"))


# -------------------------------------------------------------------------
# stats.total_alerts_processed counts each submission
# -------------------------------------------------------------------------
reset()
section("stats.total_alerts_processed counts each submission")

post_route("route-all", conditions={})

post_alert(id="alert-1")
post_alert(id="alert-1")  # re-submission
post_alert(id="alert-1")  # re-submission again
post_alert(id="alert-2")  # different alert

stats = requests.get(f"{BASE_URL}/stats").json()
check("total_alerts_processed counts all submissions including re-submissions",
    stats["total_alerts_processed"] == 4, stats.get("total_alerts_processed"))


# -------------------------------------------------------------------------
# Re-submission with suppression
# -------------------------------------------------------------------------
reset()
section("Re-submission interacts correctly with suppression")

post_route("route-1", conditions={}, suppression_window_seconds=300)

first = post_alert(id="alert-1")
check("First submission routes", first["suppressed"] is False, first.get("suppressed"))

# Re-submitting the same alert ID — suppression window is still active
second = post_alert(id="alert-1")
check("Re-submission of same alert within window is suppressed", second["suppressed"] is True, second.get("suppressed"))

# Different alert ID, same service — also suppressed
third = post_alert(id="alert-2", service="payment-api")
check("Different alert ID, same service within window is suppressed", third["suppressed"] is True, third.get("suppressed"))

# Different service — not suppressed
fourth = post_alert(id="alert-3", service="auth-service")
check("Different service not suppressed despite same route", fourth["suppressed"] is False, fourth.get("suppressed"))


# -------------------------------------------------------------------------
# Multiple re-submissions — only one alert record
# -------------------------------------------------------------------------
reset()
section("Multiple re-submissions produce one alert record in GET /alerts")

post_route("route-all", conditions={})

for i in range(5):
    post_alert(id="alert-1", severity="critical", description=f"attempt {i}")

r = requests.get(f"{BASE_URL}/alerts").json()
check("5 re-submissions of same ID still shows 1 alert in list", r["total"] == 1, r.get("total"))
check("Alert ID in list matches the submitted ID", r["alerts"][0]["alert_id"] == "alert-1", r.get("alerts"))


# -------------------------------------------------------------------------
# Re-submission with changed service field — suppression re-keyed on new service
# -------------------------------------------------------------------------
reset()
section("Re-submission with changed service — suppression keyed on new service")

post_route("route-1", conditions={}, suppression_window_seconds=300)

# First submission — service=payment-api opens suppression window for payment-api
first = post_alert(id="alert-1", service="payment-api")
check("First submission (payment-api) routes normally", first["suppressed"] is False, first.get("suppressed"))

# Re-submit same alert ID but with service=auth-service
# auth-service has no open suppression window — should route normally
second = post_alert(id="alert-1", service="auth-service")
check("Re-submission with new service (auth-service) routes normally (no window for auth-service)", second["suppressed"] is False, second.get("suppressed"))
check("Re-submission with new service routes to route-1", second["routed_to"] is not None and second["routed_to"]["route_id"] == "route-1", second.get("routed_to"))

# Now auth-service has a window open. A fresh alert for auth-service should be suppressed.
third = post_alert(id="alert-99", service="auth-service")
check("New alert for auth-service suppressed (window opened by re-submission)", third["suppressed"] is True, third.get("suppressed"))

# Original service (payment-api) window is still open — new alert for it should be suppressed
fourth = post_alert(id="alert-98", service="payment-api")
check("New alert for payment-api still suppressed (original window intact)", fourth["suppressed"] is True, fourth.get("suppressed"))


# -------------------------------------------------------------------------
# Re-submission alongside a new unique alert
# -------------------------------------------------------------------------
reset()
section("Re-submissions don't affect other alert IDs")

post_route("route-all", conditions={})

post_alert(id="alert-1")
post_alert(id="alert-2")
post_alert(id="alert-1")  # re-submission of alert-1

r = requests.get(f"{BASE_URL}/alerts").json()
check("Two distinct alert IDs in list despite 3 submissions", r["total"] == 2, r.get("total"))

ids = {a["alert_id"] for a in r["alerts"]}
check("Both alert IDs present", ids == {"alert-1", "alert-2"}, ids)


# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
total = passed + failed
print(f"\n{'='*50}")
print(f"Section 8 — Alert Re-submission: {passed}/{total} passed", "✓" if failed == 0 else "✗")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
