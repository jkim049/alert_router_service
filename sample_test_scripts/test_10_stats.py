#!/usr/bin/env python3
"""
Section 10: Stats
Covers:
  - Empty state: all zeros
  - total_alerts_processed = total_routed + total_suppressed + total_unrouted
  - total_routed, total_suppressed, total_unrouted counts
  - by_severity breakdown
  - by_service breakdown
  - by_route breakdown (total_matched, total_routed, total_suppressed)
  - Re-submissions counted in totals
  - Unrouted alerts don't appear in by_route
  - Stats reset after POST /reset
  - by_route.total_matched = total_routed + total_suppressed per route
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


def stats():
    return requests.get(f"{BASE_URL}/stats").json()


# -------------------------------------------------------------------------
# Empty state
# -------------------------------------------------------------------------
reset()
section("Empty state — all zeros")

s = stats()
check("GET /stats returns 200", requests.get(f"{BASE_URL}/stats").status_code == 200)
check("total_alerts_processed is 0", s["total_alerts_processed"] == 0, s.get("total_alerts_processed"))
check("total_routed is 0", s["total_routed"] == 0, s.get("total_routed"))
check("total_suppressed is 0", s["total_suppressed"] == 0, s.get("total_suppressed"))
check("total_unrouted is 0", s["total_unrouted"] == 0, s.get("total_unrouted"))
check("by_severity is empty", s["by_severity"] == {}, s.get("by_severity"))
check("by_service is empty", s["by_service"] == {}, s.get("by_service"))
check("by_route is empty", s["by_route"] == {}, s.get("by_route"))


# -------------------------------------------------------------------------
# Response shape
# -------------------------------------------------------------------------
reset()
section("Response shape")

s = stats()
for field in ["total_alerts_processed", "total_routed", "total_suppressed",
              "total_unrouted", "by_severity", "by_service", "by_route"]:
    check(f"Stats response includes '{field}'", field in s, list(s.keys()))

post_route("route-1", conditions={}, suppression_window_seconds=300)
post_alert("a1")
post_alert("a2")   # suppressed
post_alert("a3", severity="warning")  # unrouted (route only matches all but let's use specific)

reset()
post_route("route-1", conditions={"severity": ["critical"]}, suppression_window_seconds=300)
post_alert("a1", severity="critical")   # routed
post_alert("a2", severity="critical")   # suppressed

s = stats()
route_stats = s["by_route"].get("route-1", {})
for field in ["total_matched", "total_routed", "total_suppressed"]:
    check(f"by_route entry includes '{field}'", field in route_stats, list(route_stats.keys()))


# -------------------------------------------------------------------------
# All three statuses counted correctly
# -------------------------------------------------------------------------
reset()
section("All three statuses: routed, suppressed, unrouted")

post_route("route-critical", conditions={"severity": ["critical"]}, suppression_window_seconds=300)
post_alert("a1", severity="critical")   # pending (routed)
post_alert("a2", severity="critical")   # suppressed
post_alert("a3", severity="warning")    # unrouted
post_alert("a4", severity="info")       # unrouted

s = stats()
check("total_routed = 1", s["total_routed"] == 1, s.get("total_routed"))
check("total_suppressed = 1", s["total_suppressed"] == 1, s.get("total_suppressed"))
check("total_unrouted = 2", s["total_unrouted"] == 2, s.get("total_unrouted"))
check("total_alerts_processed = 4", s["total_alerts_processed"] == 4, s.get("total_alerts_processed"))
check("total_alerts_processed = routed + suppressed + unrouted",
    s["total_alerts_processed"] == s["total_routed"] + s["total_suppressed"] + s["total_unrouted"], s)


# -------------------------------------------------------------------------
# total_alerts_processed counts re-submissions
# -------------------------------------------------------------------------
reset()
section("total_alerts_processed counts re-submissions")

post_route("route-all", conditions={})
post_alert("a1")
post_alert("a1")  # re-submission
post_alert("a1")  # re-submission again
post_alert("a2")

s = stats()
check("total_alerts_processed = 4 (includes re-submissions)", s["total_alerts_processed"] == 4, s.get("total_alerts_processed"))


# -------------------------------------------------------------------------
# by_severity
# -------------------------------------------------------------------------
reset()
section("by_severity breakdown")

post_route("route-all", conditions={})
post_alert("a1", severity="critical")
post_alert("a2", severity="critical")
post_alert("a3", severity="critical")
post_alert("a4", severity="warning")
post_alert("a5", severity="warning")
post_alert("a6", severity="info")

s = stats()
check("by_severity.critical = 3", s["by_severity"].get("critical") == 3, s.get("by_severity"))
check("by_severity.warning = 2", s["by_severity"].get("warning") == 2, s.get("by_severity"))
check("by_severity.info = 1", s["by_severity"].get("info") == 1, s.get("by_severity"))
check("by_severity has no extra keys", set(s["by_severity"].keys()) == {"critical", "warning", "info"}, s.get("by_severity"))

# Severity not seen should not appear
reset()
post_route("route-all", conditions={})
post_alert("a1", severity="critical")
post_alert("a2", severity="warning")

s = stats()
check("Unseen severity 'info' absent from by_severity", "info" not in s["by_severity"], s.get("by_severity"))


# -------------------------------------------------------------------------
# by_service
# -------------------------------------------------------------------------
reset()
section("by_service breakdown")

post_route("route-all", conditions={})
post_alert("a1", service="payment-api")
post_alert("a2", service="payment-api")
post_alert("a3", service="auth-service")
post_alert("a4", service="auth-service")
post_alert("a5", service="auth-service")
post_alert("a6", service="orders-api")

s = stats()
check("by_service.payment-api = 2", s["by_service"].get("payment-api") == 2, s.get("by_service"))
check("by_service.auth-service = 3", s["by_service"].get("auth-service") == 3, s.get("by_service"))
check("by_service.orders-api = 1", s["by_service"].get("orders-api") == 1, s.get("by_service"))
check("by_service has no extra keys", set(s["by_service"].keys()) == {"payment-api", "auth-service", "orders-api"}, s.get("by_service"))

# Service not seen should not appear
reset()
post_route("route-all", conditions={})
post_alert("a1", service="payment-api")

s = stats()
check("Unseen service absent from by_service", "auth-service" not in s["by_service"], s.get("by_service"))


# -------------------------------------------------------------------------
# by_route
# -------------------------------------------------------------------------
reset()
section("by_route breakdown")

post_route("route-a", conditions={"severity": ["critical"]}, priority=20, suppression_window_seconds=300)
post_route("route-b", conditions={"severity": ["critical", "warning"]}, priority=10, suppression_window_seconds=300)

# a1 → route-a (pending), suppresses route-a for payment-api
post_alert("a1", severity="critical", service="payment-api")
# a2 → route-a suppressed, falls through to route-b (pending)
post_alert("a2", severity="critical", service="payment-api")
# a3 → both suppressed, reported against route-a (suppressed)
post_alert("a3", severity="critical", service="payment-api")
# a4 → route-b only (warning doesn't match route-a)
post_alert("a4", severity="warning", service="auth-service")
# a5 → unrouted
post_alert("a5", severity="info", service="orders-api")

s = stats()
ra = s["by_route"].get("route-a", {})
rb = s["by_route"].get("route-b", {})

check("by_route.route-a.total_routed = 1", ra.get("total_routed") == 1, ra)
check("by_route.route-a.total_suppressed = 1", ra.get("total_suppressed") == 1, ra)
check("by_route.route-a.total_matched = 2", ra.get("total_matched") == 2, ra)
check("by_route.route-a: total_matched = routed + suppressed",
    ra.get("total_matched") == ra.get("total_routed", 0) + ra.get("total_suppressed", 0), ra)

check("by_route.route-b.total_routed = 2", rb.get("total_routed") == 2, rb)
check("by_route.route-b.total_suppressed = 0", rb.get("total_suppressed") == 0, rb)
check("by_route.route-b.total_matched = 2", rb.get("total_matched") == 2, rb)

check("Unrouted alerts do not appear in by_route", "unrouted-route" not in s["by_route"], s.get("by_route"))


# -------------------------------------------------------------------------
# Unrouted alerts do not appear in by_route
# -------------------------------------------------------------------------
reset()
section("Unrouted alerts excluded from by_route")

post_route("route-critical", conditions={"severity": ["critical"]})
post_alert("a1", severity="critical")   # routed
post_alert("a2", severity="warning")    # unrouted
post_alert("a3", severity="info")       # unrouted

s = stats()
check("by_route only contains route-critical", set(s["by_route"].keys()) == {"route-critical"}, s.get("by_route"))
check("total_unrouted = 2", s["total_unrouted"] == 2, s.get("total_unrouted"))


# -------------------------------------------------------------------------
# Multiple routes — each tracked independently in by_route
# -------------------------------------------------------------------------
reset()
section("Multiple routes tracked independently in by_route")

post_route("route-x", conditions={"severity": ["critical"]}, priority=10)
post_route("route-y", conditions={"severity": ["warning"]}, priority=10)
post_route("route-z", conditions={"severity": ["info"]}, priority=10)

post_alert("a1", severity="critical")
post_alert("a2", severity="critical")
post_alert("a3", severity="warning")
post_alert("a4", severity="info")
post_alert("a5", severity="info")

s = stats()
check("route-x.total_routed = 2", s["by_route"].get("route-x", {}).get("total_routed") == 2, s["by_route"].get("route-x"))
check("route-y.total_routed = 1", s["by_route"].get("route-y", {}).get("total_routed") == 1, s["by_route"].get("route-y"))
check("route-z.total_routed = 2", s["by_route"].get("route-z", {}).get("total_routed") == 2, s["by_route"].get("route-z"))


# -------------------------------------------------------------------------
# Stats reset after POST /reset
# -------------------------------------------------------------------------
reset()
section("Stats reset after POST /reset")

post_route("route-all", conditions={})
for i in range(5):
    post_alert(f"a{i}")

s = stats()
check("Stats non-zero before reset", s["total_alerts_processed"] == 5, s.get("total_alerts_processed"))

reset()
s = stats()
check("total_alerts_processed = 0 after reset", s["total_alerts_processed"] == 0, s.get("total_alerts_processed"))
check("total_routed = 0 after reset", s["total_routed"] == 0, s.get("total_routed"))
check("by_severity empty after reset", s["by_severity"] == {}, s.get("by_severity"))
check("by_service empty after reset", s["by_service"] == {}, s.get("by_service"))
check("by_route empty after reset", s["by_route"] == {}, s.get("by_route"))


# -------------------------------------------------------------------------
# by_route total_matched invariant across all routes
# -------------------------------------------------------------------------
reset()
section("by_route invariant: total_matched == total_routed + total_suppressed for every route")

post_route("route-p", conditions={"severity": ["critical"]}, priority=20, suppression_window_seconds=300)
post_route("route-q", conditions={}, priority=10, suppression_window_seconds=300)

# Various alerts creating routed and suppressed states across both routes
post_alert("b1", severity="critical", service="svc-a")   # → route-p, opens window on svc-a
post_alert("b2", severity="critical", service="svc-a")   # → route-p suppressed (falls to route-q), opens window on svc-a for route-q
post_alert("b3", severity="critical", service="svc-a")   # → both suppressed, reported against route-p
post_alert("b4", severity="warning",  service="svc-b")   # → route-q only
post_alert("b5", severity="warning",  service="svc-b")   # → route-q suppressed

s = stats()
for route_id, route_stats in s["by_route"].items():
    check(
        f"by_route[{route_id}]: total_matched == total_routed + total_suppressed",
        route_stats.get("total_matched") == route_stats.get("total_routed", 0) + route_stats.get("total_suppressed", 0),
        route_stats,
    )


# -------------------------------------------------------------------------
# Stats when route deleted mid-session
# -------------------------------------------------------------------------
reset()
section("Stats when route deleted mid-session")

post_route("route-del", conditions={})
post_alert("d1", severity="critical")
post_alert("d2", severity="warning")

s = stats()
check("Stats include route-del before deletion", "route-del" in s["by_route"], s.get("by_route"))
check("total_alerts_processed = 2 before deletion", s["total_alerts_processed"] == 2, s.get("total_alerts_processed"))

requests.delete(f"{BASE_URL}/routes/route-del")

# Top-level counters should still reflect the two processed alerts
s = stats()
check("total_alerts_processed unchanged after route deletion", s["total_alerts_processed"] == 2, s.get("total_alerts_processed"))
check("total_routed unchanged after route deletion", s["total_routed"] == 2, s.get("total_routed"))

# New alert with no routes — unrouted
post_alert("d3", severity="critical")
s = stats()
check("total_alerts_processed incremented after route deletion", s["total_alerts_processed"] == 3, s.get("total_alerts_processed"))
check("total_unrouted = 1 after route deleted and new alert submitted", s["total_unrouted"] == 1, s.get("total_unrouted"))


# -------------------------------------------------------------------------
# Invariants
# -------------------------------------------------------------------------
reset()
section("Invariants across all counters")

post_route("route-critical", conditions={"severity": ["critical"]}, suppression_window_seconds=300)
post_alert("a1", severity="critical")
post_alert("a2", severity="critical")
post_alert("a3", severity="warning")

s = stats()
check("total_alerts_processed == sum of all status counts",
    s["total_alerts_processed"] == s["total_routed"] + s["total_suppressed"] + s["total_unrouted"], s)

total_from_severity = sum(s["by_severity"].values())
check("Sum of by_severity == total_alerts_processed",
    total_from_severity == s["total_alerts_processed"], {"by_severity_sum": total_from_severity, "total": s["total_alerts_processed"]})

total_from_service = sum(s["by_service"].values())
check("Sum of by_service == total_alerts_processed",
    total_from_service == s["total_alerts_processed"], {"by_service_sum": total_from_service, "total": s["total_alerts_processed"]})


# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
total = passed + failed
print(f"\n{'='*50}")
print(f"Section 10 — Stats: {passed}/{total} passed", "✓" if failed == 0 else "✗")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
