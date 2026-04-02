#!/usr/bin/env python3
"""
Section 3: Basic Routing
Covers:
  - Alert matching a single route
  - Alert matching multiple routes → highest priority wins
  - Priority tiebreaker (alphabetical ID)
  - Unrouted alerts (no routes, no match)
  - matched_routes contains ALL matching route IDs
  - evaluation_details counts are correct
  - Response shape
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


def post_route(id, conditions, target_type="slack", priority=10, **kwargs):
    targets = {
        "slack": {"type": "slack", "channel": f"#{id}"},
        "email": {"type": "email", "address": f"{id}@example.com"},
        "pagerduty": {"type": "pagerduty", "service_key": f"pd-{id}"},
        "webhook": {"type": "webhook", "url": f"https://hooks.example.com/{id}"},
    }
    payload = {
        "id": id,
        "conditions": conditions,
        "target": targets[target_type],
        "priority": priority,
        **kwargs,
    }
    requests.post(f"{BASE_URL}/routes", json=payload)


def post_alert(id="alert-1", severity="critical", service="payment-api", group="backend",
               timestamp="2026-03-25T14:30:00Z", **kwargs):
    return requests.post(f"{BASE_URL}/alerts", json={
        "id": id, "severity": severity, "service": service,
        "group": group, "timestamp": timestamp, **kwargs,
    }).json()


# -------------------------------------------------------------------------
# Unrouted — no routes exist
# -------------------------------------------------------------------------
reset()
section("Unrouted — no routes configured")

data = post_alert()
check("Status 200", requests.post(f"{BASE_URL}/alerts", json={
    "id": "alert-x", "severity": "critical", "service": "svc", "group": "grp",
    "timestamp": "2026-03-25T14:30:00Z",
}).status_code == 200)
check("routed_to is null when no routes exist", data["routed_to"] is None, data.get("routed_to"))
check("matched_routes is empty when no routes exist", data["matched_routes"] == [], data.get("matched_routes"))
check("suppressed is false when unrouted", data["suppressed"] is False, data.get("suppressed"))
check("suppression_reason is null when unrouted", data["suppression_reason"] is None, data.get("suppression_reason"))
check("total_routes_evaluated is 0 when no routes", data["evaluation_details"]["total_routes_evaluated"] == 0, data["evaluation_details"])
check("routes_matched is 0 when no routes", data["evaluation_details"]["routes_matched"] == 0, data["evaluation_details"])
check("routes_not_matched is 0 when no routes", data["evaluation_details"]["routes_not_matched"] == 0, data["evaluation_details"])
check("suppression_applied is false when unrouted", data["evaluation_details"]["suppression_applied"] is False, data["evaluation_details"])


# -------------------------------------------------------------------------
# Unrouted — routes exist but none match
# -------------------------------------------------------------------------
reset()
section("Unrouted — routes exist but none match")

post_route("route-critical", {"severity": ["critical"]}, priority=10)
post_route("route-backend", {"group": ["backend"]}, priority=5)

data = post_alert(severity="info", group="frontend")  # matches neither
check("routed_to is null when no conditions match", data["routed_to"] is None, data.get("routed_to"))
check("matched_routes is empty when no conditions match", data["matched_routes"] == [], data.get("matched_routes"))
check("suppressed is false when unrouted", data["suppressed"] is False, data.get("suppressed"))
check("total_routes_evaluated is 2", data["evaluation_details"]["total_routes_evaluated"] == 2, data["evaluation_details"])
check("routes_matched is 0", data["evaluation_details"]["routes_matched"] == 0, data["evaluation_details"])
check("routes_not_matched is 2", data["evaluation_details"]["routes_not_matched"] == 2, data["evaluation_details"])


# -------------------------------------------------------------------------
# Single route match
# -------------------------------------------------------------------------
reset()
section("Single route match")

post_route("route-only", {"severity": ["critical"]}, target_type="slack", priority=10)

data = post_alert(severity="critical")
check("routed_to is not null", data["routed_to"] is not None, data.get("routed_to"))
check("routed_to.route_id matches the route", data["routed_to"]["route_id"] == "route-only", data.get("routed_to"))
check("routed_to.target.type is slack", data["routed_to"]["target"]["type"] == "slack", data.get("routed_to"))
check("suppressed is false", data["suppressed"] is False, data.get("suppressed"))
check("matched_routes contains the matched route", data["matched_routes"] == ["route-only"], data.get("matched_routes"))
check("total_routes_evaluated is 1", data["evaluation_details"]["total_routes_evaluated"] == 1, data["evaluation_details"])
check("routes_matched is 1", data["evaluation_details"]["routes_matched"] == 1, data["evaluation_details"])
check("routes_not_matched is 0", data["evaluation_details"]["routes_not_matched"] == 0, data["evaluation_details"])
check("suppression_applied is false", data["evaluation_details"]["suppression_applied"] is False, data["evaluation_details"])


# -------------------------------------------------------------------------
# Multiple routes — highest priority wins
# -------------------------------------------------------------------------
reset()
section("Multiple matching routes — highest priority wins")

post_route("route-low", {}, target_type="slack", priority=5)
post_route("route-mid", {}, target_type="email", priority=50)
post_route("route-high", {}, target_type="pagerduty", priority=100)

data = post_alert()
check("Winner is highest priority route", data["routed_to"]["route_id"] == "route-high", data.get("routed_to"))
check("Winner target is pagerduty", data["routed_to"]["target"]["type"] == "pagerduty", data.get("routed_to"))
check("matched_routes includes all 3 matching routes", set(data["matched_routes"]) == {"route-low", "route-mid", "route-high"}, data.get("matched_routes"))
check("routes_matched is 3", data["evaluation_details"]["routes_matched"] == 3, data["evaluation_details"])
check("routes_not_matched is 0", data["evaluation_details"]["routes_not_matched"] == 0, data["evaluation_details"])
check("total_routes_evaluated is 3", data["evaluation_details"]["total_routes_evaluated"] == 3, data["evaluation_details"])


# -------------------------------------------------------------------------
# Multiple routes — partial match
# -------------------------------------------------------------------------
reset()
section("Multiple routes — only some match")

post_route("route-critical", {"severity": ["critical"]}, priority=10)
post_route("route-warning", {"severity": ["warning"]}, priority=20)
post_route("route-info", {"severity": ["info"]}, priority=30)
post_route("route-all", {}, priority=5)

data = post_alert(severity="critical")  # matches route-critical and route-all
check("Winner is highest priority matching route", data["routed_to"]["route_id"] == "route-critical", data.get("routed_to"))
check("matched_routes contains only matching routes", set(data["matched_routes"]) == {"route-critical", "route-all"}, data.get("matched_routes"))
check("routes_matched is 2", data["evaluation_details"]["routes_matched"] == 2, data["evaluation_details"])
check("routes_not_matched is 2", data["evaluation_details"]["routes_not_matched"] == 2, data["evaluation_details"])
check("total_routes_evaluated is 4", data["evaluation_details"]["total_routes_evaluated"] == 4, data["evaluation_details"])


# -------------------------------------------------------------------------
# Priority tiebreaker — alphabetical ID
# -------------------------------------------------------------------------
reset()
section("Priority tiebreaker — alphabetical ID (lowest wins)")

post_route("route-z", {}, target_type="slack", priority=10)
post_route("route-m", {}, target_type="email", priority=10)
post_route("route-a", {}, target_type="pagerduty", priority=10)

data = post_alert()
check("Alphabetically lowest ID wins on equal priority", data["routed_to"]["route_id"] == "route-a", data.get("routed_to"))

# Confirm it's not just insertion order
reset()
post_route("route-a", {}, target_type="pagerduty", priority=10)
post_route("route-m", {}, target_type="email", priority=10)
post_route("route-z", {}, target_type="slack", priority=10)

data = post_alert()
check("Tiebreaker is alphabetical regardless of insertion order", data["routed_to"]["route_id"] == "route-a", data.get("routed_to"))


# -------------------------------------------------------------------------
# Priority ordering edge cases
# -------------------------------------------------------------------------
reset()
section("Priority ordering edge cases")

post_route("route-negative", {}, target_type="slack", priority=-10)
post_route("route-zero", {}, target_type="email", priority=0)
post_route("route-positive", {}, target_type="pagerduty", priority=1)

data = post_alert()
check("Positive priority beats zero and negative", data["routed_to"]["route_id"] == "route-positive", data.get("routed_to"))

reset()
post_route("route-large", {}, target_type="pagerduty", priority=9999)
post_route("route-small", {}, target_type="slack", priority=1)

data = post_alert()
check("Largest priority value wins", data["routed_to"]["route_id"] == "route-large", data.get("routed_to"))


# -------------------------------------------------------------------------
# Response shape
# -------------------------------------------------------------------------
reset()
section("Response shape")

post_route("route-shape", {"severity": ["critical"]}, target_type="slack", priority=10)
data = post_alert(severity="critical")

check("Response includes 'alert_id'", "alert_id" in data, list(data.keys()))
check("alert_id matches submitted id", data["alert_id"] == "alert-1", data.get("alert_id"))
check("Response includes 'routed_to'", "routed_to" in data, list(data.keys()))
check("routed_to includes 'route_id'", "route_id" in data["routed_to"], data.get("routed_to"))
check("routed_to includes 'target'", "target" in data["routed_to"], data.get("routed_to"))
check("Response includes 'suppressed'", "suppressed" in data, list(data.keys()))
check("Response includes 'suppression_reason'", "suppression_reason" in data, list(data.keys()))
check("Response includes 'matched_routes'", "matched_routes" in data, list(data.keys()))
check("matched_routes is a list", isinstance(data["matched_routes"], list), type(data.get("matched_routes")))
check("Response includes 'evaluation_details'", "evaluation_details" in data, list(data.keys()))
details = data["evaluation_details"]
for field in ["total_routes_evaluated", "routes_matched", "routes_not_matched", "suppression_applied"]:
    check(f"evaluation_details includes '{field}'", field in details, list(details.keys()))

# Unrouted response shape
data_unrouted = post_alert(id="alert-unrouted", severity="info")
check("Unrouted: routed_to is null (not missing)", "routed_to" in data_unrouted and data_unrouted["routed_to"] is None, data_unrouted)
check("Unrouted: matched_routes is [] (not null)", data_unrouted["matched_routes"] == [], data_unrouted.get("matched_routes"))
check("Unrouted: suppression_reason is null", data_unrouted["suppression_reason"] is None, data_unrouted.get("suppression_reason"))



# -------------------------------------------------------------------------
# Counts are consistent
# -------------------------------------------------------------------------
reset()
section("Counts consistency")

post_route("r1", {"severity": ["critical"]}, priority=30)
post_route("r2", {"severity": ["critical", "warning"]}, priority=20)
post_route("r3", {"severity": ["warning"]}, priority=10)
post_route("r4", {"severity": ["info"]}, priority=40)

data = post_alert(severity="critical")  # matches r1, r2
details = data["evaluation_details"]
check("routes_matched + routes_not_matched == total_routes_evaluated",
    details["routes_matched"] + details["routes_not_matched"] == details["total_routes_evaluated"],
    details)
check("len(matched_routes) == routes_matched",
    len(data["matched_routes"]) == details["routes_matched"],
    data)
check("Winner route_id is in matched_routes",
    data["routed_to"]["route_id"] in data["matched_routes"],
    data)


# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
total = passed + failed
print(f"\n{'='*50}")
print(f"Section 3 — Basic Routing: {passed}/{total} passed", "✓" if failed == 0 else "✗")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
