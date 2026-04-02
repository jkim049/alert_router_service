#!/usr/bin/env python3
"""
Section 11: Dry-run (POST /test)
Covers:
  - Returns correct routing result for a matched alert
  - Returns unrouted result when no route matches
  - Does not persist the alert (GET /alerts/{id} returns 404)
  - Does not affect GET /alerts list
  - Does not affect suppression state
  - Does not affect stats
  - Response shape matches POST /alerts response shape
  - Suppression logic reflected in dry-run result (without persisting)
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


def post_alert(id, severity="critical", service="payment-api", group="backend",
               timestamp="2026-03-25T14:30:00Z"):
    return requests.post(f"{BASE_URL}/alerts", json={
        "id": id, "severity": severity, "service": service,
        "group": group, "timestamp": timestamp,
    }).json()


def dry_run(id, severity="critical", service="payment-api", group="backend",
            timestamp="2026-03-25T14:30:00Z"):
    return requests.post(f"{BASE_URL}/test", json={
        "id": id, "severity": severity, "service": service,
        "group": group, "timestamp": timestamp,
    })


def stats():
    return requests.get(f"{BASE_URL}/stats").json()


# -------------------------------------------------------------------------
# Basic dry-run — matched route
# -------------------------------------------------------------------------
reset()
section("Dry-run returns correct routing result (matched)")

post_route("route-critical", conditions={"severity": ["critical"]}, priority=10)

r = dry_run("test-alert-1", severity="critical")
check("POST /test returns 200", r.status_code == 200, r.status_code)

data = r.json()
check("routed_to is set", data["routed_to"] is not None, data.get("routed_to"))
check("routed_to.route_id is correct", data["routed_to"]["route_id"] == "route-critical", data.get("routed_to"))
check("suppressed is False", data["suppressed"] is False, data.get("suppressed"))
check("alert_id is correct", data["alert_id"] == "test-alert-1", data.get("alert_id"))


# -------------------------------------------------------------------------
# Basic dry-run — unrouted
# -------------------------------------------------------------------------
reset()
section("Dry-run returns unrouted when no route matches")

post_route("route-critical", conditions={"severity": ["critical"]})

r = dry_run("test-no-match", severity="info")
check("POST /test returns 200 for unrouted", r.status_code == 200, r.status_code)

data = r.json()
check("routed_to is null for unrouted", data["routed_to"] is None, data.get("routed_to"))
check("suppressed is False for unrouted", data["suppressed"] is False, data.get("suppressed"))
check("matched_routes is empty for unrouted", data["matched_routes"] == [], data.get("matched_routes"))


# -------------------------------------------------------------------------
# Response shape matches POST /alerts
# -------------------------------------------------------------------------
reset()
section("Response shape matches POST /alerts")

post_route("route-all", conditions={})

real = post_alert("real-alert-1")
dry = dry_run("dry-alert-1").json()

for field in ["alert_id", "routed_to", "suppressed", "suppression_reason",
              "matched_routes", "evaluation_details"]:
    check(f"dry-run response includes '{field}'", field in dry, list(dry.keys()))

# evaluation_details sub-fields
ed = dry.get("evaluation_details", {})
for field in ["total_routes_evaluated", "suppression_applied"]:
    check(f"evaluation_details includes '{field}'", field in ed, list(ed.keys()))


# -------------------------------------------------------------------------
# Does not persist the alert
# -------------------------------------------------------------------------
reset()
section("Dry-run does not persist the alert")

post_route("route-all", conditions={})

dry_run("ghost-alert", severity="critical")

r = requests.get(f"{BASE_URL}/alerts/ghost-alert")
check("GET /alerts/{id} returns 404 after dry-run", r.status_code == 404, r.status_code)

r = requests.get(f"{BASE_URL}/alerts").json()
check("GET /alerts list is empty after dry-run only", r["total"] == 0, r.get("total"))
check("alerts list contains no dry-run entries", r["alerts"] == [], r.get("alerts"))


# -------------------------------------------------------------------------
# Does not affect existing alerts list
# -------------------------------------------------------------------------
reset()
section("Dry-run does not affect existing alerts list")

post_route("route-all", conditions={})
post_alert("real-1")
post_alert("real-2")

dry_run("dry-extra")

r = requests.get(f"{BASE_URL}/alerts").json()
check("List still contains only 2 real alerts", r["total"] == 2, r.get("total"))
ids = {a["alert_id"] for a in r["alerts"]}
check("dry-run alert not in list", "dry-extra" not in ids, ids)
check("real alerts still present", {"real-1", "real-2"} == ids, ids)


# -------------------------------------------------------------------------
# Does not affect stats
# -------------------------------------------------------------------------
reset()
section("Dry-run does not affect stats")

post_route("route-all", conditions={})

# Baseline: no alerts submitted yet
s_before = stats()
check("Stats zero before dry-run", s_before["total_alerts_processed"] == 0, s_before.get("total_alerts_processed"))

dry_run("dry-stat-1", severity="critical", service="payment-api")
dry_run("dry-stat-2", severity="warning", service="auth-service")
dry_run("dry-stat-3", severity="info",     service="orders-api")

s_after = stats()
check("total_alerts_processed unchanged after dry-runs", s_after["total_alerts_processed"] == 0, s_after.get("total_alerts_processed"))
check("total_routed unchanged after dry-runs", s_after["total_routed"] == 0, s_after.get("total_routed"))
check("total_unrouted unchanged after dry-runs", s_after["total_unrouted"] == 0, s_after.get("total_unrouted"))
check("by_severity empty after dry-runs", s_after["by_severity"] == {}, s_after.get("by_severity"))
check("by_service empty after dry-runs", s_after["by_service"] == {}, s_after.get("by_service"))
check("by_route empty after dry-runs", s_after["by_route"] == {}, s_after.get("by_route"))

# Mix: real alert then dry-run — only real alert counted
post_alert("real-counted")
s_mixed = stats()
check("Only real alert counted in stats", s_mixed["total_alerts_processed"] == 1, s_mixed.get("total_alerts_processed"))


# -------------------------------------------------------------------------
# Does not affect suppression state
# -------------------------------------------------------------------------
reset()
section("Dry-run does not affect suppression state")

post_route("route-1", conditions={}, suppression_window_seconds=300)

# Dry-run multiple times — should not set suppression window
for i in range(3):
    dry_run(f"dry-suppress-{i}", service="payment-api")

# Real alert should route (not be suppressed) because dry-runs don't set suppression
real = post_alert("real-first", service="payment-api")
check("First real alert not suppressed (dry-runs didn't set window)", real["suppressed"] is False, real.get("suppressed"))
check("First real alert routes normally", real["routed_to"] is not None, real.get("routed_to"))

# Now real alert has set suppression — next real alert should be suppressed
real2 = post_alert("real-second", service="payment-api")
check("Second real alert suppressed (first real alert set window)", real2["suppressed"] is True, real2.get("suppressed"))

# Dry-run after suppression is set — should show suppressed in result but not renew window
dry_result = dry_run("dry-during-suppress", service="payment-api").json()
check("Dry-run reflects suppression state in result", dry_result["suppressed"] is True, dry_result.get("suppressed"))


# -------------------------------------------------------------------------
# Dry-run with multiple routes — priority respected
# -------------------------------------------------------------------------
reset()
section("Dry-run respects route priority")

post_route("route-high", conditions={"severity": ["critical"]}, priority=20)
post_route("route-low",  conditions={}, priority=5)

data = dry_run("dry-priority", severity="critical").json()
check("Dry-run routes to highest priority match", data["routed_to"]["route_id"] == "route-high", data.get("routed_to"))
check("matched_routes includes both routes", set(data["matched_routes"]) == {"route-high", "route-low"}, data.get("matched_routes"))

data = dry_run("dry-priority-low", severity="info").json()
check("Dry-run with info routes to low-priority catch-all", data["routed_to"]["route_id"] == "route-low", data.get("routed_to"))


# -------------------------------------------------------------------------
# Dry-run does not create suppression even when window would trigger
# -------------------------------------------------------------------------
reset()
section("Dry-run suppression result is read-only — does not persist suppression")

post_route("route-1", conditions={}, suppression_window_seconds=300)

# First dry-run "routes" — should not open a suppression window
dr1 = dry_run("dry-open", service="payment-api").json()
check("First dry-run shows not suppressed", dr1["suppressed"] is False, dr1.get("suppressed"))

# Second dry-run — should still show not suppressed (no window was opened)
dr2 = dry_run("dry-open-2", service="payment-api").json()
check("Second dry-run still shows not suppressed (window not persisted)", dr2["suppressed"] is False, dr2.get("suppressed"))

# Real alert — should route, not be suppressed
real = post_alert("real-open", service="payment-api")
check("Real alert routes normally (dry-run didn't open suppression window)", real["suppressed"] is False, real.get("suppressed"))


# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
total = passed + failed
print(f"\n{'='*50}")
print(f"Section 11 — Dry-run (POST /test): {passed}/{total} passed", "✓" if failed == 0 else "✗")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
