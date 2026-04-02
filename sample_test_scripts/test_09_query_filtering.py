#!/usr/bin/env python3
"""
Section 9: Query & Filtering
Covers:
  - GET /alerts/{id} happy path and 404
  - GET /alerts with no filters
  - Filtering by service, severity, routed, suppressed
  - Combined filters
  - total field always matches len(alerts)
  - Ordering (id ASC)
  - Edge cases: empty results, contradictory filters
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


def get_alerts(**params):
    return requests.get(f"{BASE_URL}/alerts", params=params).json()


# -------------------------------------------------------------------------
# GET /alerts/{id} — happy path
# -------------------------------------------------------------------------
reset()
section("GET /alerts/{id} — happy path")

post_route("route-1", conditions={"severity": ["critical"]})
post_result = post_alert(id="alert-1", severity="critical")

r = requests.get(f"{BASE_URL}/alerts/alert-1")
check("GET /alerts/{id} returns 200", r.status_code == 200, r.status_code)

data = r.json()
check("Response matches POST response exactly", data == post_result, {"get": data, "post": post_result})
check("alert_id is correct", data["alert_id"] == "alert-1", data.get("alert_id"))
check("routed_to is set", data["routed_to"] is not None, data.get("routed_to"))
check("routed_to.route_id is correct", data["routed_to"]["route_id"] == "route-1", data.get("routed_to"))
check("suppressed is False", data["suppressed"] is False, data.get("suppressed"))
check("matched_routes is a list", isinstance(data["matched_routes"], list), data.get("matched_routes"))
check("evaluation_details is present", "evaluation_details" in data, list(data.keys()))


# -------------------------------------------------------------------------
# GET /alerts/{id} — 404
# -------------------------------------------------------------------------
reset()
section("GET /alerts/{id} — 404 for missing alert")

r = requests.get(f"{BASE_URL}/alerts/does-not-exist")
check("Missing alert returns 404", r.status_code == 404, r.status_code)
check("404 response has 'error' key", "error" in r.json(), r.json())

# Deleted alert (via reset) is also 404
post_alert(id="alert-gone")
reset()
r = requests.get(f"{BASE_URL}/alerts/alert-gone")
check("Alert 404 after reset", r.status_code == 404, r.status_code)


# -------------------------------------------------------------------------
# GET /alerts — empty state
# -------------------------------------------------------------------------
reset()
section("GET /alerts — empty state")

r = get_alerts()
check("Empty state returns 200", requests.get(f"{BASE_URL}/alerts").status_code == 200)
check("Empty state: alerts is []", r["alerts"] == [], r.get("alerts"))
check("Empty state: total is 0", r["total"] == 0, r.get("total"))


# -------------------------------------------------------------------------
# GET /alerts — no filters, all alerts returned
# -------------------------------------------------------------------------
reset()
section("GET /alerts — no filters returns all alerts")

post_route("route-all", conditions={})
for i in range(4):
    post_alert(id=f"alert-{i}")

r = get_alerts()
check("All 4 alerts returned with no filter", r["total"] == 4, r.get("total"))
check("total matches len(alerts)", r["total"] == len(r["alerts"]), r)


# -------------------------------------------------------------------------
# GET /alerts — ordering
# -------------------------------------------------------------------------
reset()
section("GET /alerts — ordered by alert ID ascending")

post_route("route-all", conditions={})
for id in ["alert-c", "alert-a", "alert-b"]:
    post_alert(id=id)

r = get_alerts()
ids = [a["alert_id"] for a in r["alerts"]]
check("Alerts returned in ascending ID order", ids == sorted(ids), ids)


# -------------------------------------------------------------------------
# Filter by service
# -------------------------------------------------------------------------
reset()
section("Filter by service")

post_route("route-all", conditions={})
post_alert(id="a1", service="payment-api")
post_alert(id="a2", service="payment-api")
post_alert(id="a3", service="auth-service")
post_alert(id="a4", service="orders-api")

r = get_alerts(service="payment-api")
check("Filter service=payment-api returns 2", r["total"] == 2, r.get("total"))
check("All returned alerts have correct service", all(a["alert_id"] in ["a1", "a2"] for a in r["alerts"]), [a["alert_id"] for a in r["alerts"]])
check("total matches len(alerts)", r["total"] == len(r["alerts"]), r)

r = get_alerts(service="auth-service")
check("Filter service=auth-service returns 1", r["total"] == 1, r.get("total"))
check("Correct alert returned", r["alerts"][0]["alert_id"] == "a3", r.get("alerts"))

r = get_alerts(service="does-not-exist")
check("Filter service=does-not-exist returns 0", r["total"] == 0, r.get("total"))
check("Empty alerts list", r["alerts"] == [], r.get("alerts"))


# -------------------------------------------------------------------------
# Filter by severity
# -------------------------------------------------------------------------
reset()
section("Filter by severity")

post_route("route-all", conditions={})
post_alert(id="a1", severity="critical")
post_alert(id="a2", severity="critical")
post_alert(id="a3", severity="warning")
post_alert(id="a4", severity="info")

r = get_alerts(severity="critical")
check("Filter severity=critical returns 2", r["total"] == 2, r.get("total"))
check("total matches len(alerts)", r["total"] == len(r["alerts"]), r)

r = get_alerts(severity="warning")
check("Filter severity=warning returns 1", r["total"] == 1, r.get("total"))

r = get_alerts(severity="info")
check("Filter severity=info returns 1", r["total"] == 1, r.get("total"))

r = get_alerts(severity="extreme")
check("Filter severity=extreme (invalid) returns 0", r["total"] == 0, r.get("total"))


# -------------------------------------------------------------------------
# Filter by routed
# -------------------------------------------------------------------------
reset()
section("Filter by routed")

post_route("route-critical", conditions={"severity": ["critical"]}, suppression_window_seconds=300)
post_alert(id="a1", severity="critical")   # pending
post_alert(id="a2", severity="critical")   # suppressed
post_alert(id="a3", severity="warning")    # unrouted
post_alert(id="a4", severity="info")       # unrouted

r = get_alerts(routed="true")
check("routed=true returns pending + suppressed", r["total"] == 2, r.get("total"))
ids = {a["alert_id"] for a in r["alerts"]}
check("routed=true includes pending alert", "a1" in ids, ids)
check("routed=true includes suppressed alert", "a2" in ids, ids)
check("routed=true excludes unrouted alerts", "a3" not in ids and "a4" not in ids, ids)
check("total matches len(alerts)", r["total"] == len(r["alerts"]), r)

r = get_alerts(routed="false")
check("routed=false returns only unrouted", r["total"] == 2, r.get("total"))
ids = {a["alert_id"] for a in r["alerts"]}
check("routed=false includes unrouted alerts", {"a3", "a4"} == ids, ids)
check("routed=false excludes pending and suppressed", "a1" not in ids and "a2" not in ids, ids)


# -------------------------------------------------------------------------
# Filter by suppressed
# -------------------------------------------------------------------------
reset()
section("Filter by suppressed")

post_route("route-critical", conditions={"severity": ["critical"]}, suppression_window_seconds=300)
post_alert(id="a1", severity="critical")   # pending
post_alert(id="a2", severity="critical")   # suppressed
post_alert(id="a3", severity="warning")    # unrouted

r = get_alerts(suppressed="true")
check("suppressed=true returns only suppressed alert", r["total"] == 1, r.get("total"))
check("suppressed=true returns correct alert", r["alerts"][0]["alert_id"] == "a2", r.get("alerts"))

r = get_alerts(suppressed="false")
check("suppressed=false returns pending + unrouted", r["total"] == 2, r.get("total"))
ids = {a["alert_id"] for a in r["alerts"]}
check("suppressed=false includes pending", "a1" in ids, ids)
check("suppressed=false includes unrouted", "a3" in ids, ids)
check("suppressed=false excludes suppressed", "a2" not in ids, ids)


# -------------------------------------------------------------------------
# Combined filters
# -------------------------------------------------------------------------
reset()
section("Combined filters")

post_route("route-critical", conditions={"severity": ["critical"]}, suppression_window_seconds=300)
post_alert(id="a1", severity="critical", service="payment-api")   # pending
post_alert(id="a2", severity="critical", service="payment-api")   # suppressed
post_alert(id="a3", severity="critical", service="auth-service")  # pending (different service)
post_alert(id="a4", severity="warning",  service="payment-api")   # unrouted

# service + severity
r = get_alerts(service="payment-api", severity="critical")
check("service=payment-api + severity=critical returns 2", r["total"] == 2, r.get("total"))
ids = {a["alert_id"] for a in r["alerts"]}
check("Correct alerts returned for service+severity", {"a1", "a2"} == ids, ids)

# service + routed=true
r = get_alerts(service="payment-api", routed="true")
check("service=payment-api + routed=true returns 2 (pending+suppressed)", r["total"] == 2, r.get("total"))

# service + routed=false
r = get_alerts(service="payment-api", routed="false")
check("service=payment-api + routed=false returns 1 (unrouted)", r["total"] == 1, r.get("total"))
check("Correct unrouted alert returned", r["alerts"][0]["alert_id"] == "a4", r.get("alerts"))

# severity + suppressed=true
r = get_alerts(severity="critical", suppressed="true")
check("severity=critical + suppressed=true returns 1", r["total"] == 1, r.get("total"))
check("Correct suppressed alert returned", r["alerts"][0]["alert_id"] == "a2", r.get("alerts"))

# service + severity + routed=true
r = get_alerts(service="payment-api", severity="critical", routed="true")
check("service + severity + routed=true returns 2", r["total"] == 2, r.get("total"))

# service + severity + suppressed=true
r = get_alerts(service="payment-api", severity="critical", suppressed="true")
check("service + severity + suppressed=true returns 1", r["total"] == 1, r.get("total"))


# -------------------------------------------------------------------------
# Contradictory filters — always empty
# -------------------------------------------------------------------------
reset()
section("Contradictory filters — always return empty")

post_route("route-critical", conditions={"severity": ["critical"]}, suppression_window_seconds=300)
post_alert(id="a1", severity="critical")   # pending
post_alert(id="a2", severity="critical")   # suppressed
post_alert(id="a3", severity="warning")    # unrouted

# routed=false means unrouted; suppressed=true means a route matched — contradiction
r = get_alerts(routed="false", suppressed="true")
check("routed=false + suppressed=true always returns empty", r["total"] == 0, r.get("total"))
check("Contradictory filters: alerts is []", r["alerts"] == [], r.get("alerts"))


# -------------------------------------------------------------------------
# List item shape matches single-item GET shape
# -------------------------------------------------------------------------
reset()
section("List item shape matches GET /alerts/{id} shape")

post_route("route-1", conditions={"severity": ["critical"]}, suppression_window_seconds=300)
post_alert(id="shape-1", severity="critical")   # routed
post_alert(id="shape-2", severity="critical")   # suppressed
post_alert(id="shape-3", severity="warning")    # unrouted

list_r = get_alerts()
single_r = requests.get(f"{BASE_URL}/alerts/shape-1").json()

required_fields = ["alert_id", "routed_to", "suppressed", "suppression_reason",
                   "matched_routes", "evaluation_details"]

for field in required_fields:
    check(f"Single GET includes '{field}'", field in single_r, list(single_r.keys()))

for item in list_r["alerts"]:
    for field in required_fields:
        check(f"List item '{item['alert_id']}' includes '{field}'", field in item, list(item.keys()))

# evaluation_details in list items must have the same sub-fields as single GET
for item in list_r["alerts"]:
    ed_item = item.get("evaluation_details", {})
    for subfield in ["total_routes_evaluated", "routes_matched", "routes_not_matched", "suppression_applied"]:
        check(f"List item '{item['alert_id']}' evaluation_details includes '{subfield}'",
              subfield in ed_item, list(ed_item.keys()))


# -------------------------------------------------------------------------
# total field consistency
# -------------------------------------------------------------------------
reset()
section("total field always matches len(alerts)")

post_route("route-all", conditions={})
for i in range(6):
    post_alert(id=f"alert-{i}", severity=["critical", "warning", "info"][i % 3])

for params in [
    {},
    {"severity": "critical"},
    {"severity": "warning"},
    {"routed": "true"},
    {"routed": "false"},
    {"service": "payment-api"},
    {"service": "nonexistent"},
]:
    r = get_alerts(**params)
    check(f"total == len(alerts) for params={params}",
        r["total"] == len(r["alerts"]), {"total": r.get("total"), "len": len(r.get("alerts", []))})


# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
total = passed + failed
print(f"\n{'='*50}")
print(f"Section 9 — Query & Filtering: {passed}/{total} passed", "✓" if failed == 0 else "✗")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
