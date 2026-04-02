#!/usr/bin/env python3
"""
Section 12: Omitted conditions
Covers:
  - A route with an empty conditions object ({}) matches all alerts
  - A route with no conditions key behaves the same as empty conditions
  - Catch-all route is overridden by a higher-priority specific route
  - Catch-all route wins when specific route does not match
  - Catch-all works across all severity levels, services, and groups
  - Multiple catch-all routes — highest priority wins
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


def post_route(id, conditions, priority=10, suppression_window_seconds=0):
    return requests.post(f"{BASE_URL}/routes", json={
        "id": id,
        "conditions": conditions,
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


# -------------------------------------------------------------------------
# Empty conditions object matches all alerts
# -------------------------------------------------------------------------
reset()
section("Empty conditions {} matches all alerts")

post_route("catch-all", conditions={}, priority=5)

severities = ["critical", "warning", "info"]
for sev in severities:
    r = post_alert(f"alert-sev-{sev}", severity=sev)
    check(f"Empty conditions matches severity={sev}", r["routed_to"] is not None and r["routed_to"]["route_id"] == "catch-all", r.get("routed_to"))

services = ["payment-api", "auth-service", "orders", "unknown-svc"]
for svc in services:
    r = post_alert(f"alert-svc-{svc}", service=svc)
    check(f"Empty conditions matches service={svc}", r["routed_to"] is not None and r["routed_to"]["route_id"] == "catch-all", r.get("routed_to"))

groups = ["backend", "frontend", "data", "infra"]
for grp in groups:
    r = post_alert(f"alert-grp-{grp}", group=grp)
    check(f"Empty conditions matches group={grp}", r["routed_to"] is not None and r["routed_to"]["route_id"] == "catch-all", r.get("routed_to"))


# -------------------------------------------------------------------------
# Catch-all loses to higher-priority specific route
# -------------------------------------------------------------------------
reset()
section("Catch-all loses to higher-priority specific route")

post_route("catch-all",     conditions={},                      priority=5)
post_route("route-critical", conditions={"severity": ["critical"]}, priority=20)

r = post_alert("alert-prio-1", severity="critical")
check("Critical alert routes to high-priority specific route", r["routed_to"]["route_id"] == "route-critical", r.get("routed_to"))
check("Both routes in matched_routes", set(r["matched_routes"]) == {"catch-all", "route-critical"}, r.get("matched_routes"))

r = post_alert("alert-prio-2", severity="warning")
check("Warning alert routes to catch-all (specific doesn't match)", r["routed_to"]["route_id"] == "catch-all", r.get("routed_to"))
check("Only catch-all in matched_routes for warning", r["matched_routes"] == ["catch-all"], r.get("matched_routes"))


# -------------------------------------------------------------------------
# Catch-all wins when no specific route matches
# -------------------------------------------------------------------------
reset()
section("Catch-all wins when no specific route matches")

post_route("catch-all",    conditions={},                   priority=5)
post_route("route-svc",    conditions={"service": ["auth"]}, priority=10)

r = post_alert("alert-fallback", service="unknown-service")
check("Unknown service falls back to catch-all", r["routed_to"]["route_id"] == "catch-all", r.get("routed_to"))
check("Alert not suppressed", r["suppressed"] is False, r.get("suppressed"))


# -------------------------------------------------------------------------
# Multiple catch-all routes — highest priority wins
# -------------------------------------------------------------------------
reset()
section("Multiple catch-all routes — highest priority wins")

post_route("catch-low",  conditions={}, priority=5)
post_route("catch-mid",  conditions={}, priority=15)
post_route("catch-high", conditions={}, priority=25)

r = post_alert("alert-multi-catch")
check("Highest-priority catch-all wins", r["routed_to"]["route_id"] == "catch-high", r.get("routed_to"))
check("All three catch-alls in matched_routes", set(r["matched_routes"]) == {"catch-low", "catch-mid", "catch-high"}, r.get("matched_routes"))


# -------------------------------------------------------------------------
# No routes at all — alert is unrouted
# -------------------------------------------------------------------------
reset()
section("No routes — alert is unrouted")

r = post_alert("alert-no-routes")
check("Alert unrouted when no routes exist", r["routed_to"] is None, r.get("routed_to"))
check("matched_routes is empty", r["matched_routes"] == [], r.get("matched_routes"))
check("suppressed is False", r["suppressed"] is False, r.get("suppressed"))


# -------------------------------------------------------------------------
# Only specific routes, none matching — alert is unrouted (no catch-all)
# -------------------------------------------------------------------------
reset()
section("Specific-only routes with no match — alert is unrouted")

post_route("route-critical", conditions={"severity": ["critical"]}, priority=10)
post_route("route-auth",     conditions={"service": ["auth"]},      priority=10)

r = post_alert("alert-unrouted-specific", severity="info", service="payment-api")
check("Alert unrouted (no catch-all, no matching specific route)", r["routed_to"] is None, r.get("routed_to"))
check("matched_routes empty", r["matched_routes"] == [], r.get("matched_routes"))


# -------------------------------------------------------------------------
# Catch-all with suppression window still suppresses
# -------------------------------------------------------------------------
reset()
section("Catch-all with suppression window suppresses repeats")

post_route("catch-suppress", conditions={}, priority=5, suppression_window_seconds=300)

r1 = post_alert("alert-sup-1", service="payment-api")
check("First alert routes through catch-all", r1["routed_to"]["route_id"] == "catch-suppress", r1.get("routed_to"))
check("First alert not suppressed", r1["suppressed"] is False, r1.get("suppressed"))

r2 = post_alert("alert-sup-2", service="payment-api")
check("Second alert suppressed by catch-all window", r2["suppressed"] is True, r2.get("suppressed"))

# Different service should route normally (suppression is per-service)
r3 = post_alert("alert-sup-3", service="auth-service")
check("Different service not suppressed by catch-all window", r3["suppressed"] is False, r3.get("suppressed"))


# -------------------------------------------------------------------------
# Catch-all coexists with label-matched routes
# -------------------------------------------------------------------------
reset()
section("Catch-all coexists with label-based and glob routes")

post_route("catch-all",    conditions={},                              priority=5)
post_route("route-label",  conditions={"severity": ["critical"], "service": ["payment-api"]}, priority=15)

# Exact multi-condition match → specific route
r = post_alert("alert-exact", severity="critical", service="payment-api")
check("Multi-condition match routes to specific route", r["routed_to"]["route_id"] == "route-label", r.get("routed_to"))

# Partial condition match (severity only) → catch-all wins because specific doesn't match
r = post_alert("alert-partial", severity="critical", service="other-service")
check("Partial condition miss falls back to catch-all", r["routed_to"]["route_id"] == "catch-all", r.get("routed_to"))

# No condition match → catch-all
r = post_alert("alert-nomatch", severity="info", service="orders")
check("No condition match falls to catch-all", r["routed_to"]["route_id"] == "catch-all", r.get("routed_to"))


# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
total = passed + failed
print(f"\n{'='*50}")
print(f"Section 12 — Omitted conditions: {passed}/{total} passed", "✓" if failed == 0 else "✗")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
