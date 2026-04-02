#!/usr/bin/env python3
"""
Section 14: Full reset (POST /reset)
Covers:
  - After POST /reset, GET /routes returns empty list
  - After POST /reset, GET /alerts returns empty list
  - After POST /reset, GET /stats returns all-zero counters
  - After POST /reset, GET /stats by_severity/by_service/by_route are empty
  - Previously created routes are not accessible after reset
  - Previously submitted alerts are not accessible after reset
  - Suppression state is cleared by reset
  - Reset is idempotent (double reset is safe)
  - Service works normally after reset (routes and alerts can be created fresh)
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
    r = requests.post(f"{BASE_URL}/reset")
    return r


def section(title):
    print(f"\n--- {title} ---")


def post_route(id, conditions=None, priority=10, suppression_window_seconds=0):
    return requests.post(f"{BASE_URL}/routes", json={
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
    })


# -------------------------------------------------------------------------
# Reset response
# -------------------------------------------------------------------------
reset()
section("POST /reset response")

r = reset()
check("POST /reset returns 200", r.status_code == 200, r.status_code)


# -------------------------------------------------------------------------
# Routes cleared
# -------------------------------------------------------------------------
reset()
section("Routes are cleared after reset")

post_route("route-a")
post_route("route-b")
post_route("route-c")

r = requests.get(f"{BASE_URL}/routes").json()
check("Three routes exist before reset", len(r) == 3, r)

reset()

r = requests.get(f"{BASE_URL}/routes").json()
check("Routes list is empty after reset", r == [], r)
check("Routes count is 0 after reset", len(r) == 0, r)

# Confirm route-a is not in the list
r = requests.get(f"{BASE_URL}/routes").json()
check("route-a not in routes list after reset", not any(rt["id"] == "route-a" for rt in r), r)


# -------------------------------------------------------------------------
# Alerts cleared
# -------------------------------------------------------------------------
reset()
section("Alerts are cleared after reset")

post_route("route-all")
post_alert("alert-1", severity="critical")
post_alert("alert-2", severity="warning")
post_alert("alert-3", severity="info")

r = requests.get(f"{BASE_URL}/alerts").json()
check("Three alerts exist before reset", r["total"] == 3, r.get("total"))

reset()

r = requests.get(f"{BASE_URL}/alerts").json()
check("Alerts list is empty after reset", r["alerts"] == [], r.get("alerts"))
check("total is 0 after reset", r["total"] == 0, r.get("total"))

# Individual alert lookup returns 404
r = requests.get(f"{BASE_URL}/alerts/alert-1")
check("GET /alerts/alert-1 returns 404 after reset", r.status_code == 404, r.status_code)


# -------------------------------------------------------------------------
# Stats zeroed
# -------------------------------------------------------------------------
reset()
section("Stats are zeroed after reset")

post_route("route-all")
post_alert("alert-s1", severity="critical", service="payment-api")
post_alert("alert-s2", severity="warning",  service="auth-service")
post_alert("alert-s3", severity="info",     service="orders-api")

s = requests.get(f"{BASE_URL}/stats").json()
check("Stats non-zero before reset", s["total_alerts_processed"] == 3, s.get("total_alerts_processed"))

reset()

s = requests.get(f"{BASE_URL}/stats").json()
check("total_alerts_processed is 0 after reset", s["total_alerts_processed"] == 0, s.get("total_alerts_processed"))
check("total_routed is 0 after reset", s["total_routed"] == 0, s.get("total_routed"))
check("total_suppressed is 0 after reset", s["total_suppressed"] == 0, s.get("total_suppressed"))
check("total_unrouted is 0 after reset", s["total_unrouted"] == 0, s.get("total_unrouted"))
check("by_severity is empty after reset", s["by_severity"] == {}, s.get("by_severity"))
check("by_service is empty after reset", s["by_service"] == {}, s.get("by_service"))
check("by_route is empty after reset", s["by_route"] == {}, s.get("by_route"))


# -------------------------------------------------------------------------
# Suppression state cleared
# -------------------------------------------------------------------------
reset()
section("Suppression state is cleared after reset")

post_route("route-suppress", suppression_window_seconds=300)
post_alert("alert-open-window", service="payment-api")

# Second alert should be suppressed
r = post_alert("alert-suppressed", service="payment-api").json()
check("Alert suppressed before reset", r["suppressed"] is True, r.get("suppressed"))

reset()

# Re-create route and submit same service — should NOT be suppressed
post_route("route-suppress", suppression_window_seconds=300)
r = post_alert("alert-after-reset", service="payment-api").json()
check("Alert not suppressed after reset (suppression window cleared)", r["suppressed"] is False, r.get("suppressed"))
check("Alert routes normally after reset", r["routed_to"] is not None, r.get("routed_to"))


# -------------------------------------------------------------------------
# Reset is idempotent
# -------------------------------------------------------------------------
reset()
section("Reset is idempotent")

r1 = reset()
check("First reset returns 200", r1.status_code == 200, r1.status_code)

r2 = reset()
check("Second consecutive reset returns 200", r2.status_code == 200, r2.status_code)

r3 = reset()
check("Third consecutive reset returns 200", r3.status_code == 200, r3.status_code)

r = requests.get(f"{BASE_URL}/routes").json()
check("Routes still empty after triple reset", r == [], r)

s = requests.get(f"{BASE_URL}/stats").json()
check("Stats still zero after triple reset", s["total_alerts_processed"] == 0, s.get("total_alerts_processed"))


# -------------------------------------------------------------------------
# Service works normally after reset
# -------------------------------------------------------------------------
reset()
section("Service is fully functional after reset")

post_route("fresh-route-1", conditions={"severity": ["critical"]}, priority=20)
post_route("fresh-route-2", conditions={}, priority=5)

r = requests.get(f"{BASE_URL}/routes").json()
check("Routes created successfully after reset", len(r) == 2, r)

a1 = post_alert("fresh-alert-1", severity="critical").json()
check("Critical alert routes to fresh-route-1 after reset", a1["routed_to"]["route_id"] == "fresh-route-1", a1.get("routed_to"))

a2 = post_alert("fresh-alert-2", severity="info").json()
check("Info alert routes to fresh-route-2 after reset", a2["routed_to"]["route_id"] == "fresh-route-2", a2.get("routed_to"))

s = requests.get(f"{BASE_URL}/stats").json()
check("Stats accumulate correctly after reset", s["total_alerts_processed"] == 2, s.get("total_alerts_processed"))
check("total_routed is 2 after reset", s["total_routed"] == 2, s.get("total_routed"))
check("by_severity populated after reset", s["by_severity"].get("critical") == 1, s.get("by_severity"))
check("by_route populated after reset", s["by_route"].get("fresh-route-1", {}).get("total_routed") == 1, s.get("by_route"))


# -------------------------------------------------------------------------
# Reset clears data created in same session (no carryover)
# -------------------------------------------------------------------------
reset()
section("Reset clears all data regardless of volume")

post_route("bulk-route")
for i in range(10):
    post_alert(f"bulk-alert-{i}", severity="critical")

r = requests.get(f"{BASE_URL}/alerts").json()
check("10 alerts exist before reset", r["total"] == 10, r.get("total"))

reset()

r = requests.get(f"{BASE_URL}/alerts").json()
check("All 10 alerts cleared by reset", r["total"] == 0, r.get("total"))

s = requests.get(f"{BASE_URL}/stats").json()
check("Stats zero after bulk reset", s["total_alerts_processed"] == 0, s.get("total_alerts_processed"))


# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
total = passed + failed
print(f"\n{'='*50}")
print(f"Section 14 — Full reset: {passed}/{total} passed", "✓" if failed == 0 else "✗")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
