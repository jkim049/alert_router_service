#!/usr/bin/env python3
"""
Section 1: Route CRUD
Covers happy path, unhappy path, and edge cases for:
  - Creating routes (all target types, all fields)
  - Listing routes (ordering, empty state)
  - Updating routes via re-POST
  - Deleting routes
  - Validation errors
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


# -------------------------------------------------------------------------
# Empty state
# -------------------------------------------------------------------------
reset()
section("Empty state")

r = requests.get(f"{BASE_URL}/routes")
check("GET /routes returns 200", r.status_code == 200, r.status_code)
check("GET /routes returns empty list on fresh state", r.json() == [], r.json())


# -------------------------------------------------------------------------
# Create — happy path (all target types)
# -------------------------------------------------------------------------
reset()
section("Create — all target types")

slack_payload = {
    "id": "route-slack",
    "conditions": {"severity": ["critical"]},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 10,
}
r = requests.post(f"{BASE_URL}/routes", json=slack_payload)
check("Create slack route returns 200", r.status_code == 200, r.status_code)
check("Create slack route returns created=True", r.json() == {"id": "route-slack", "created": True}, r.json())

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-email",
    "conditions": {"severity": ["warning"]},
    "target": {"type": "email", "address": "ops@example.com"},
    "priority": 20,
})
check("Create email route returns created=True", r.json().get("created") is True, r.json())

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-pagerduty",
    "conditions": {"group": ["backend"]},
    "target": {"type": "pagerduty", "service_key": "pd-key-123"},
    "priority": 30,
})
check("Create pagerduty route returns created=True", r.json().get("created") is True, r.json())

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-webhook",
    "conditions": {},
    "target": {"type": "webhook", "url": "https://hooks.example.com/alert"},
    "priority": 5,
})
check("Create webhook route (no headers) returns created=True", r.json().get("created") is True, r.json())

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-webhook-headers",
    "conditions": {},
    "target": {
        "type": "webhook",
        "url": "https://hooks.example.com/alert",
        "headers": {"Authorization": "Bearer token123", "X-Custom": "value"},
    },
    "priority": 4,
})
check("Create webhook route (with headers) returns created=True", r.json().get("created") is True, r.json())


# -------------------------------------------------------------------------
# Create — optional fields
# -------------------------------------------------------------------------
reset()
section("Create — optional fields")

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-minimal",
    "conditions": {},
    "target": {"type": "slack", "channel": "#general"},
    "priority": 1,
})
check("Route with no suppression_window_seconds defaults to 0", r.status_code == 200, r.status_code)
route = requests.get(f"{BASE_URL}/routes").json()[0]
check("suppression_window_seconds defaults to 0", route["suppression_window_seconds"] == 0, route.get("suppression_window_seconds"))
check("active_hours defaults to null", route["active_hours"] is None, route.get("active_hours"))

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-with-suppression",
    "conditions": {"severity": ["critical"]},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 10,
    "suppression_window_seconds": 300,
})
check("Route with suppression_window_seconds=300 accepted", r.status_code == 200, r.status_code)

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-with-active-hours",
    "conditions": {},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 10,
    "active_hours": {"timezone": "America/New_York", "start": "09:00", "end": "17:00"},
})
check("Route with active_hours accepted", r.status_code == 200, r.status_code)
routes = requests.get(f"{BASE_URL}/routes").json()
route_with_hours = next(r for r in routes if r["id"] == "route-with-active-hours")
check("active_hours persisted correctly", route_with_hours["active_hours"] == {
    "timezone": "America/New_York", "start": "09:00", "end": "17:00"
}, route_with_hours.get("active_hours"))


# -------------------------------------------------------------------------
# Create — response shape
# -------------------------------------------------------------------------
reset()
section("Create — response shape")

requests.post(f"{BASE_URL}/routes", json={
    "id": "route-shape",
    "conditions": {"severity": ["critical"]},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 10,
    "suppression_window_seconds": 60,
})
routes = requests.get(f"{BASE_URL}/routes").json()
route = routes[0]
for field in ["id", "conditions", "target", "priority", "suppression_window_seconds", "active_hours", "created_at", "updated_at"]:
    check(f"Route response includes '{field}'", field in route, list(route.keys()))


# -------------------------------------------------------------------------
# List — ordering
# -------------------------------------------------------------------------
reset()
section("List — ordering")

for rid in ["route-c", "route-a", "route-b"]:
    requests.post(f"{BASE_URL}/routes", json={
        "id": rid,
        "conditions": {},
        "target": {"type": "slack", "channel": "#oncall"},
        "priority": 1,
    })

routes = requests.get(f"{BASE_URL}/routes").json()
ids = [r["id"] for r in routes]
check("Routes returned in ascending ID order", ids == sorted(ids), ids)
check("All 3 routes present", len(routes) == 3, len(routes))


# -------------------------------------------------------------------------
# Update (re-POST)
# -------------------------------------------------------------------------
reset()
section("Update via re-POST")

requests.post(f"{BASE_URL}/routes", json={
    "id": "route-1",
    "conditions": {"severity": ["critical"]},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 10,
})

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-1",
    "conditions": {"severity": ["warning"]},
    "target": {"type": "email", "address": "ops@example.com"},
    "priority": 99,
    "suppression_window_seconds": 600,
})
check("Re-POST existing route returns 200", r.status_code == 200, r.status_code)
check("Re-POST returns created=False", r.json() == {"id": "route-1", "created": False}, r.json())

routes = requests.get(f"{BASE_URL}/routes").json()
updated = routes[0]
check("Priority updated", updated["priority"] == 99, updated.get("priority"))
check("Target updated", updated["target"]["type"] == "email", updated.get("target"))
check("Conditions updated", updated["conditions"].get("severity") == ["warning"], updated.get("conditions"))
check("suppression_window_seconds updated", updated["suppression_window_seconds"] == 600, updated.get("suppression_window_seconds"))
check("Only one route exists after upsert", len(routes) == 1, len(routes))

# Re-POST multiple times — still only one route
for i in range(3):
    requests.post(f"{BASE_URL}/routes", json={
        "id": "route-1",
        "conditions": {},
        "target": {"type": "slack", "channel": f"#channel-{i}"},
        "priority": i,
    })
routes = requests.get(f"{BASE_URL}/routes").json()
check("Multiple re-POSTs don't create duplicate routes", len(routes) == 1, len(routes))
check("Last re-POST value is persisted", routes[0]["target"]["channel"] == "#channel-2", routes[0].get("target"))


# -------------------------------------------------------------------------
# Delete — happy path
# -------------------------------------------------------------------------
reset()
section("Delete — happy path")

requests.post(f"{BASE_URL}/routes", json={
    "id": "route-to-delete",
    "conditions": {},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 1,
})

r = requests.delete(f"{BASE_URL}/routes/route-to-delete")
check("DELETE returns 200", r.status_code == 200, r.status_code)
check("DELETE returns correct shape", r.json() == {"id": "route-to-delete", "deleted": True}, r.json())

routes = requests.get(f"{BASE_URL}/routes").json()
check("Route no longer appears in list after deletion", routes == [], routes)

# Delete and recreate — should return created=True again
r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-to-delete",
    "conditions": {},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 1,
})
check("Recreating deleted route returns created=True", r.json().get("created") is True, r.json())


# -------------------------------------------------------------------------
# Delete — 404 on missing route
# -------------------------------------------------------------------------
reset()
section("Delete — 404 on missing")

r = requests.delete(f"{BASE_URL}/routes/does-not-exist")
check("DELETE non-existent route returns 404", r.status_code == 404, r.status_code)

# Delete already-deleted route
requests.post(f"{BASE_URL}/routes", json={
    "id": "route-once",
    "conditions": {},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 1,
})
requests.delete(f"{BASE_URL}/routes/route-once")
r = requests.delete(f"{BASE_URL}/routes/route-once")
check("DELETE already-deleted route returns 404", r.status_code == 404, r.status_code)


# -------------------------------------------------------------------------
# Validation errors
# -------------------------------------------------------------------------
reset()
section("Validation errors — missing required fields")

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-x",
    "conditions": {},
    "target": {"type": "slack", "channel": "#oncall"},
    # missing priority
})
check("Missing priority returns 400", r.status_code == 400, r.status_code)
check("Missing priority error body has 'error' key", "error" in r.json(), r.json())

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-x",
    "conditions": {},
    # missing target
    "priority": 10,
})
check("Missing target returns 400", r.status_code == 400, r.status_code)

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-x",
    # missing conditions
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 10,
})
check("Missing conditions returns 400", r.status_code == 400, r.status_code)

section("Validation errors — invalid field values")

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-x",
    "conditions": {},
    "target": {"type": "telegram", "chat_id": "123"},
    "priority": 10,
})
check("Invalid target type returns 400", r.status_code == 400, r.status_code)

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-x",
    "conditions": {},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 10,
    "suppression_window_seconds": -1,
})
check("Negative suppression_window_seconds returns 400", r.status_code == 400, r.status_code)

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-x",
    "conditions": {},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 10,
    "active_hours": {"timezone": "Not/ATimezone", "start": "09:00", "end": "17:00"},
})
check("Invalid timezone returns 400", r.status_code == 400, r.status_code)

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-x",
    "conditions": {},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 10,
    "active_hours": {"timezone": "UTC", "start": "9:00", "end": "17:00"},  # missing leading zero
})
check("Invalid time format (missing leading zero) returns 400", r.status_code == 400, r.status_code)

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-x",
    "conditions": {},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 10,
    "active_hours": {"timezone": "UTC", "start": "25:00", "end": "17:00"},  # invalid hour
})
check("Invalid time value (hour > 23) returns 400", r.status_code == 400, r.status_code)

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-x",
    "conditions": {},
    "target": {"type": "slack"},  # missing required channel
    "priority": 10,
})
check("Slack target missing channel returns 400", r.status_code == 400, r.status_code)

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-x",
    "conditions": {},
    "target": {"type": "email"},  # missing required address
    "priority": 10,
})
check("Email target missing address returns 400", r.status_code == 400, r.status_code)

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-x",
    "conditions": {},
    "target": {"type": "pagerduty"},  # missing required service_key
    "priority": 10,
})
check("PagerDuty target missing service_key returns 400", r.status_code == 400, r.status_code)

r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-x",
    "conditions": {},
    "target": {"type": "webhook"},  # missing required url
    "priority": 10,
})
check("Webhook target missing url returns 400", r.status_code == 400, r.status_code)


# -------------------------------------------------------------------------
# Edge cases
# -------------------------------------------------------------------------
reset()
section("Edge cases")

# suppression_window_seconds=0 is valid (no suppression)
r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-zero-suppression",
    "conditions": {},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 1,
    "suppression_window_seconds": 0,
})
check("suppression_window_seconds=0 is valid", r.status_code == 200, r.status_code)

# Overnight active_hours window
r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-overnight",
    "conditions": {},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 1,
    "active_hours": {"timezone": "UTC", "start": "22:00", "end": "06:00"},
})
check("Overnight active_hours window (start > end) is valid", r.status_code == 200, r.status_code)

# All condition fields specified at once
r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-all-conditions",
    "conditions": {
        "severity": ["critical", "warning"],
        "service": ["payment-*", "auth-service"],
        "group": ["backend"],
        "labels": {"env": "prod"},
    },
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 1,
})
check("Route with all condition fields is valid", r.status_code == 200, r.status_code)

# Empty conditions matches everything
r = requests.post(f"{BASE_URL}/routes", json={
    "id": "route-empty-conditions",
    "conditions": {},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 1,
})
check("Route with empty conditions {} is valid", r.status_code == 200, r.status_code)

# Clear all routes one by one
reset()
for rid in ["r1", "r2", "r3"]:
    requests.post(f"{BASE_URL}/routes", json={
        "id": rid, "conditions": {}, "target": {"type": "slack", "channel": "#oncall"}, "priority": 1,
    })
for rid in ["r1", "r2", "r3"]:
    requests.delete(f"{BASE_URL}/routes/{rid}")
check("Deleting all routes one by one leaves empty list", requests.get(f"{BASE_URL}/routes").json() == [], requests.get(f"{BASE_URL}/routes").json())


# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
total = passed + failed
print(f"\n{'='*50}")
print(f"Section 1 — Route CRUD: {passed}/{total} passed", "✓" if failed == 0 else "✗")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
