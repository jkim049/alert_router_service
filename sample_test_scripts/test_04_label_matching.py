#!/usr/bin/env python3
"""
Section 4: Label Matching
Covers:
  - All condition labels must be present in the alert (subset match)
  - Extra labels on the alert are fine
  - Missing label keys mean no match
  - Wrong label values mean no match
  - No labels on alert when route requires labels
  - Multiple label conditions (all must match)
  - Labels combined with other condition fields
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


def post_route(id, labels, priority=10):
    requests.post(f"{BASE_URL}/routes", json={
        "id": id,
        "conditions": {"labels": labels},
        "target": {"type": "slack", "channel": f"#{id}"},
        "priority": priority,
    })


def post_alert(id="alert-1", labels=None, **kwargs):
    payload = {
        "id": id,
        "severity": "critical",
        "service": "payment-api",
        "group": "backend",
        "timestamp": "2026-03-25T14:30:00Z",
    }
    if labels is not None:
        payload["labels"] = labels
    payload.update(kwargs)
    return requests.post(f"{BASE_URL}/alerts", json=payload).json()


def routed(data):
    return data["routed_to"] is not None


# -------------------------------------------------------------------------
# Exact label match
# -------------------------------------------------------------------------
reset()
section("Exact label match")

post_route("route-env", {"env": "prod"})

data = post_alert(id="a1", labels={"env": "prod"})
check("Exact single label match routes", routed(data), data.get("routed_to"))

data = post_alert(id="a2", labels={"env": "staging"})
check("Wrong label value does not match", not routed(data), data.get("routed_to"))

data = post_alert(id="a3", labels={"env": "PROD"})
check("Label value match is case-sensitive", not routed(data), data.get("routed_to"))

data = post_alert(id="a4", labels={"env": "prod "})
check("Label value with trailing space does not match", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Subset match — extra labels on alert are allowed
# -------------------------------------------------------------------------
reset()
section("Subset match — extra labels on alert are fine")

post_route("route-env", {"env": "prod"})

data = post_alert(id="a1", labels={"env": "prod", "region": "us-east-1"})
check("Alert with extra label still matches", routed(data), data.get("routed_to"))

data = post_alert(id="a2", labels={"env": "prod", "region": "us-east-1", "team": "payments", "version": "1.2.3"})
check("Alert with many extra labels still matches", routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Missing label key means no match
# -------------------------------------------------------------------------
reset()
section("Missing label key — no match")

post_route("route-env", {"env": "prod"})

data = post_alert(id="a1", labels={"region": "us-east-1"})
check("Alert missing required label key does not match", not routed(data), data.get("routed_to"))

data = post_alert(id="a2", labels={})
check("Alert with empty labels does not match", not routed(data), data.get("routed_to"))

data = post_alert(id="a3")  # no labels field at all
check("Alert with no labels field does not match", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Multiple label conditions — all must match
# -------------------------------------------------------------------------
reset()
section("Multiple label conditions — all must be present and correct")

post_route("route-multi", {"env": "prod", "team": "payments"})

data = post_alert(id="a1", labels={"env": "prod", "team": "payments"})
check("Both required labels present → match", routed(data), data.get("routed_to"))

data = post_alert(id="a2", labels={"env": "prod"})
check("Only one of two required labels → no match", not routed(data), data.get("routed_to"))

data = post_alert(id="a3", labels={"team": "payments"})
check("Other one of two required labels → no match", not routed(data), data.get("routed_to"))

data = post_alert(id="a4", labels={"env": "prod", "team": "platform"})
check("First label correct, second wrong value → no match", not routed(data), data.get("routed_to"))

data = post_alert(id="a5", labels={"env": "staging", "team": "payments"})
check("Second label correct, first wrong value → no match", not routed(data), data.get("routed_to"))

data = post_alert(id="a6", labels={"env": "prod", "team": "payments", "region": "eu-west-1"})
check("Both required labels + extra label → match", routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Wrong label values
# -------------------------------------------------------------------------
reset()
section("Wrong label values")

post_route("route-env", {"env": "prod"})

for wrong_value in ["staging", "dev", "test", "production", "PROD", "Prod", ""]:
    data = post_alert(id=f"a-{wrong_value or 'empty'}", labels={"env": wrong_value})
    check(f"Wrong env value '{wrong_value}' does not match", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Labels combined with other condition fields
# -------------------------------------------------------------------------
reset()
section("Labels combined with other condition fields")

requests.post(f"{BASE_URL}/routes", json={
    "id": "route-combined",
    "conditions": {
        "severity": ["critical"],
        "labels": {"env": "prod"},
    },
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 10,
})

data = post_alert(id="a1", severity="critical", labels={"env": "prod"})
check("Matching severity + labels → match", routed(data), data.get("routed_to"))

data = post_alert(id="a2", severity="warning", labels={"env": "prod"})
check("Wrong severity, correct labels → no match", not routed(data), data.get("routed_to"))

data = post_alert(id="a3", severity="critical", labels={"env": "staging"})
check("Correct severity, wrong labels → no match", not routed(data), data.get("routed_to"))

data = post_alert(id="a4", severity="critical")
check("Correct severity, no labels → no match", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Route with no label condition matches everything
# -------------------------------------------------------------------------
reset()
section("Route with no label condition")

requests.post(f"{BASE_URL}/routes", json={
    "id": "route-no-labels",
    "conditions": {"severity": ["critical"]},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 10,
})

data = post_alert(id="a1", severity="critical")
check("Route with no label condition matches alert with no labels", routed(data), data.get("routed_to"))

data = post_alert(id="a2", severity="critical", labels={"env": "prod", "team": "payments"})
check("Route with no label condition matches alert with labels", routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Multiple routes — label specificity does not affect priority
# -------------------------------------------------------------------------
reset()
section("Multiple routes with different label conditions")

requests.post(f"{BASE_URL}/routes", json={
    "id": "route-specific",
    "conditions": {"labels": {"env": "prod", "team": "payments"}},
    "target": {"type": "pagerduty", "service_key": "pd-key"},
    "priority": 10,
})
requests.post(f"{BASE_URL}/routes", json={
    "id": "route-broad",
    "conditions": {"labels": {"env": "prod"}},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 20,
})

data = post_alert(id="a1", labels={"env": "prod", "team": "payments"})
check("Higher priority route wins even if less specific", data["routed_to"]["route_id"] == "route-broad", data.get("routed_to"))
check("Both matching routes in matched_routes", set(data["matched_routes"]) == {"route-specific", "route-broad"}, data.get("matched_routes"))

data = post_alert(id="a2", labels={"env": "prod"})
check("Only broad route matches when team label absent", data["routed_to"]["route_id"] == "route-broad", data.get("routed_to"))
check("Only one route in matched_routes", data["matched_routes"] == ["route-broad"], data.get("matched_routes"))


# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
total = passed + failed
print(f"\n{'='*50}")
print(f"Section 4 — Label Matching: {passed}/{total} passed", "✓" if failed == 0 else "✗")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
