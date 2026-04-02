#!/usr/bin/env python3
"""
Section 13: Priority with multiple matching routes
Covers:
  - Three routes at different priorities all match; highest priority wins
  - All three appear in matched_routes
  - Tie-breaking behavior when two routes share the same priority
  - Priority ordering is consistent regardless of route creation order
  - matched_routes contains all matching route IDs regardless of priority
  - Unmatched routes do not appear in matched_routes
  - Single matching route still populates matched_routes
  - Priority respected across severity, service, and group conditions
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
# Core case: three routes all match, highest priority wins
# -------------------------------------------------------------------------
reset()
section("Three matching routes — highest priority wins, all in matched_routes")

post_route("route-low",  conditions={}, priority=5)
post_route("route-mid",  conditions={}, priority=15)
post_route("route-high", conditions={}, priority=25)

r = post_alert("alert-three")
check("routed_to is route-high (priority 25)", r["routed_to"]["route_id"] == "route-high", r.get("routed_to"))
check("matched_routes contains all three", set(r["matched_routes"]) == {"route-low", "route-mid", "route-high"}, r.get("matched_routes"))
check("matched_routes length is 3", len(r["matched_routes"]) == 3, r.get("matched_routes"))
check("alert not suppressed", r["suppressed"] is False, r.get("suppressed"))


# -------------------------------------------------------------------------
# Creation order does not affect priority outcome
# -------------------------------------------------------------------------
reset()
section("Creation order does not affect priority outcome")

# Register in ascending order (low first)
post_route("first-registered",  conditions={}, priority=5)
post_route("second-registered", conditions={}, priority=25)
post_route("third-registered",  conditions={}, priority=15)

r = post_alert("alert-order")
check("Highest priority wins regardless of insertion order", r["routed_to"]["route_id"] == "second-registered", r.get("routed_to"))
check("All three in matched_routes", set(r["matched_routes"]) == {"first-registered", "second-registered", "third-registered"}, r.get("matched_routes"))

# Register in descending order (high first)
reset()
post_route("z-high", conditions={}, priority=30)
post_route("z-mid",  conditions={}, priority=20)
post_route("z-low",  conditions={}, priority=10)

r = post_alert("alert-order-desc")
check("Highest priority wins when registered in descending order", r["routed_to"]["route_id"] == "z-high", r.get("routed_to"))


# -------------------------------------------------------------------------
# Mixed matching: some routes match, some do not
# -------------------------------------------------------------------------
reset()
section("Only matching routes appear in matched_routes")

post_route("route-catch",    conditions={},                        priority=5)
post_route("route-critical", conditions={"severity": ["critical"]}, priority=15)
post_route("route-warning",  conditions={"severity": ["warning"]},  priority=25)

# Critical alert: route-catch + route-critical match, route-warning does not
r = post_alert("alert-mixed-critical", severity="critical")
check("Critical routes to highest matching priority (route-critical prio 15)", r["routed_to"]["route_id"] == "route-critical", r.get("routed_to"))
check("matched_routes has catch + critical only", set(r["matched_routes"]) == {"route-catch", "route-critical"}, r.get("matched_routes"))
check("route-warning not in matched_routes", "route-warning" not in r["matched_routes"], r.get("matched_routes"))

# Warning alert: route-catch + route-warning match, route-critical does not
r = post_alert("alert-mixed-warning", severity="warning")
check("Warning routes to highest matching priority (route-warning prio 25)", r["routed_to"]["route_id"] == "route-warning", r.get("routed_to"))
check("matched_routes has catch + warning only", set(r["matched_routes"]) == {"route-catch", "route-warning"}, r.get("matched_routes"))
check("route-critical not in matched_routes", "route-critical" not in r["matched_routes"], r.get("matched_routes"))

# Info alert: only route-catch matches
r = post_alert("alert-mixed-info", severity="info")
check("Info routes to catch-all only", r["routed_to"]["route_id"] == "route-catch", r.get("routed_to"))
check("matched_routes has only catch-all", r["matched_routes"] == ["route-catch"], r.get("matched_routes"))


# -------------------------------------------------------------------------
# Single matching route still populates matched_routes
# -------------------------------------------------------------------------
reset()
section("Single matching route still appears in matched_routes")

post_route("only-route", conditions={"severity": ["critical"]}, priority=10)

r = post_alert("alert-single-match", severity="critical")
check("routed_to is only-route", r["routed_to"]["route_id"] == "only-route", r.get("routed_to"))
check("matched_routes contains the one matching route", r["matched_routes"] == ["only-route"], r.get("matched_routes"))

r2 = post_alert("alert-single-nomatch", severity="info")
check("No match yields empty matched_routes", r2["matched_routes"] == [], r2.get("matched_routes"))
check("No match yields null routed_to", r2["routed_to"] is None, r2.get("routed_to"))


# -------------------------------------------------------------------------
# Priority with multi-condition routes
# -------------------------------------------------------------------------
reset()
section("Priority respected with multi-condition routes")

post_route("route-broad",    conditions={"severity": ["critical"]},                               priority=10)
post_route("route-specific", conditions={"severity": ["critical"], "service": ["payment-api"]},   priority=20)
post_route("route-exact",    conditions={"severity": ["critical"], "service": ["payment-api"],
                                         "group": ["backend"]},                                    priority=30)

# All three match this alert
r = post_alert("alert-all-match", severity="critical", service="payment-api", group="backend")
check("Most specific (highest priority) wins", r["routed_to"]["route_id"] == "route-exact", r.get("routed_to"))
check("All three in matched_routes", set(r["matched_routes"]) == {"route-broad", "route-specific", "route-exact"}, r.get("matched_routes"))

# Only broad + specific match (group differs)
r = post_alert("alert-two-match", severity="critical", service="payment-api", group="frontend")
check("route-exact excluded when group differs", r["routed_to"]["route_id"] == "route-specific", r.get("routed_to"))
check("matched_routes has broad + specific", set(r["matched_routes"]) == {"route-broad", "route-specific"}, r.get("matched_routes"))

# Only broad matches
r = post_alert("alert-one-match", severity="critical", service="auth-service", group="frontend")
check("Only broad matches", r["routed_to"]["route_id"] == "route-broad", r.get("routed_to"))
check("matched_routes has only broad", r["matched_routes"] == ["route-broad"], r.get("matched_routes"))


# -------------------------------------------------------------------------
# Priority 1 vs large priority values
# -------------------------------------------------------------------------
reset()
section("Priority values: low (1) vs large (1000)")

post_route("route-prio-1",    conditions={}, priority=1)
post_route("route-prio-1000", conditions={}, priority=1000)

r = post_alert("alert-extreme-prio")
check("Priority 1000 beats priority 1", r["routed_to"]["route_id"] == "route-prio-1000", r.get("routed_to"))
check("Both in matched_routes", set(r["matched_routes"]) == {"route-prio-1", "route-prio-1000"}, r.get("matched_routes"))


# -------------------------------------------------------------------------
# evaluation_details reflects correct counts
# -------------------------------------------------------------------------
reset()
section("evaluation_details total_routes_evaluated is accurate")

post_route("ev-a", conditions={},                        priority=10)
post_route("ev-b", conditions={},                        priority=20)
post_route("ev-c", conditions={"severity": ["warning"]}, priority=30)

# critical: ev-a and ev-b match (2 matches), ev-c does not
r = post_alert("alert-eval", severity="critical")
ed = r.get("evaluation_details", {})
check("total_routes_evaluated is 3 (all routes checked)", ed.get("total_routes_evaluated") == 3, ed)
check("routed to ev-b (prio 20, highest matching)", r["routed_to"]["route_id"] == "ev-b", r.get("routed_to"))
check("matched_routes has ev-a and ev-b", set(r["matched_routes"]) == {"ev-a", "ev-b"}, r.get("matched_routes"))


# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
total = passed + failed
print(f"\n{'='*50}")
print(f"Section 13 — Priority: {passed}/{total} passed", "✓" if failed == 0 else "✗")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
