#!/usr/bin/env python3
"""
Section 6: Suppression Windows
Covers:
  - First alert routes normally
  - Second alert same service within window is suppressed
  - Alert after window expires routes again
  - Different service on same route is not suppressed
  - suppression_window_seconds=0 never suppresses
  - Suppression response shape (routed_to still set, suppression_reason present)
  - Suppression is per (route, service) — independent across routes
  - Fallthrough: suppressed top route falls through to next match
  - All routes suppressed → suppressed against highest priority
  - Suppression clears after reset
"""

import sys
import time
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


def post_route(id, suppression_window_seconds=300, conditions=None, priority=10, target_type="slack"):
    targets = {
        "slack":     {"type": "slack", "channel": f"#{id}"},
        "email":     {"type": "email", "address": f"{id}@example.com"},
        "pagerduty": {"type": "pagerduty", "service_key": f"pd-{id}"},
    }
    requests.post(f"{BASE_URL}/routes", json={
        "id": id,
        "conditions": conditions or {},
        "target": targets[target_type],
        "priority": priority,
        "suppression_window_seconds": suppression_window_seconds,
    })


def post_alert(id, service="payment-api", severity="critical"):
    return requests.post(f"{BASE_URL}/alerts", json={
        "id": id,
        "severity": severity,
        "service": service,
        "group": "backend",
        "timestamp": "2026-03-25T14:30:00Z",
    }).json()


# -------------------------------------------------------------------------
# Basic suppression: first routes, second suppressed
# -------------------------------------------------------------------------
reset()
section("Basic suppression: first routes, second suppressed")

post_route("route-1", suppression_window_seconds=300)

first = post_alert("a1", service="payment-api")
check("First alert routes normally", first["suppressed"] is False, first.get("suppressed"))
check("First alert routed_to is set", first["routed_to"] is not None, first.get("routed_to"))
check("First alert routed_to.route_id is correct", first["routed_to"]["route_id"] == "route-1", first.get("routed_to"))

second = post_alert("a2", service="payment-api")
check("Second alert same service is suppressed", second["suppressed"] is True, second.get("suppressed"))
check("Suppressed alert routed_to is still set", second["routed_to"] is not None, second.get("routed_to"))
check("Suppressed alert routed_to.route_id identifies suppressing route", second["routed_to"]["route_id"] == "route-1", second.get("routed_to"))
check("suppression_reason is present", second["suppression_reason"] is not None, second.get("suppression_reason"))
check("suppression_reason mentions service", "payment-api" in second["suppression_reason"], second.get("suppression_reason"))
check("suppression_reason mentions route", "route-1" in second["suppression_reason"], second.get("suppression_reason"))
check("suppression_applied is True in evaluation_details", second["evaluation_details"]["suppression_applied"] is True, second.get("evaluation_details"))

third = post_alert("a3", service="payment-api")
check("Third alert same service still suppressed", third["suppressed"] is True, third.get("suppressed"))


# -------------------------------------------------------------------------
# Window expiry: routes again after window
# -------------------------------------------------------------------------
reset()
section("Window expiry: routes again after window expires (2s window)")

post_route("route-1", suppression_window_seconds=2)

first = post_alert("a1", service="payment-api")
check("First alert routes normally", first["suppressed"] is False, first.get("suppressed"))

second = post_alert("a2", service="payment-api")
check("Second alert suppressed within window", second["suppressed"] is True, second.get("suppressed"))

print("      (waiting 3s for suppression window to expire...)")
time.sleep(3)

third = post_alert("a3", service="payment-api")
check("Third alert routes again after window expires", third["suppressed"] is False, third.get("suppressed"))
check("Third alert routed_to is set", third["routed_to"] is not None, third.get("routed_to"))


# -------------------------------------------------------------------------
# Different service — not suppressed
# -------------------------------------------------------------------------
reset()
section("Different service on same route is not suppressed")

post_route("route-1", suppression_window_seconds=300)

post_alert("a1", service="payment-api")   # sets suppression for payment-api

data = post_alert("a2", service="auth-service")
check("Different service is not suppressed", data["suppressed"] is False, data.get("suppressed"))
check("Different service routes normally", data["routed_to"] is not None, data.get("routed_to"))

data = post_alert("a3", service="orders-api")
check("Third distinct service is not suppressed", data["suppressed"] is False, data.get("suppressed"))

# Original service still suppressed
data = post_alert("a4", service="payment-api")
check("Original service still suppressed", data["suppressed"] is True, data.get("suppressed"))


# -------------------------------------------------------------------------
# suppression_window_seconds=0 — never suppresses
# -------------------------------------------------------------------------
reset()
section("suppression_window_seconds=0 — never suppresses")

post_route("route-1", suppression_window_seconds=0)

for i in range(4):
    data = post_alert(f"a{i}", service="payment-api")
    check(f"Alert {i+1} with window=0 is never suppressed", data["suppressed"] is False, data.get("suppressed"))


# -------------------------------------------------------------------------
# Suppression is per route — independent across routes
# -------------------------------------------------------------------------
reset()
section("Suppression is independent per route")

post_route("route-a", suppression_window_seconds=300, priority=20)
post_route("route-b", suppression_window_seconds=300, priority=10)

# First alert — routes to route-a (highest priority), sets suppression on route-a
first = post_alert("a1", service="payment-api")
check("First alert routes to highest priority route", first["routed_to"]["route_id"] == "route-a", first.get("routed_to"))

# Second alert — route-a suppressed, falls through to route-b, sets suppression on route-b
second = post_alert("a2", service="payment-api")
check("Second alert falls through to route-b", second["routed_to"]["route_id"] == "route-b", second.get("routed_to"))
check("Second alert is not suppressed (fell through)", second["suppressed"] is False, second.get("suppressed"))

# Third alert — both suppressed, reported against highest priority
third = post_alert("a3", service="payment-api")
check("Third alert is suppressed (all routes suppressed)", third["suppressed"] is True, third.get("suppressed"))
check("Third alert reported against highest priority route", third["routed_to"]["route_id"] == "route-a", third.get("routed_to"))


# -------------------------------------------------------------------------
# All matching routes suppressed
# -------------------------------------------------------------------------
reset()
section("All matching routes suppressed — reported against highest priority")

post_route("route-high", suppression_window_seconds=300, priority=100)
post_route("route-low",  suppression_window_seconds=300, priority=10)

post_alert("a1")  # suppresses route-high
post_alert("a2")  # falls through, suppresses route-low

third = post_alert("a3")
check("All suppressed: reported against highest priority", third["routed_to"]["route_id"] == "route-high", third.get("routed_to"))
check("All suppressed: suppressed=True", third["suppressed"] is True, third.get("suppressed"))
check("All suppressed: suppression_reason present", third["suppression_reason"] is not None, third.get("suppression_reason"))


# -------------------------------------------------------------------------
# Suppression window resets after reset
# -------------------------------------------------------------------------
reset()
section("Suppression clears after POST /reset")

post_route("route-1", suppression_window_seconds=300)
post_alert("a1", service="payment-api")  # sets suppression

data = post_alert("a2", service="payment-api")
check("Suppressed before reset", data["suppressed"] is True, data.get("suppressed"))

reset()
post_route("route-1", suppression_window_seconds=300)
data = post_alert("a3", service="payment-api")
check("Routes normally after reset", data["suppressed"] is False, data.get("suppressed"))


# -------------------------------------------------------------------------
# Suppression window renewed on each successful routing
# -------------------------------------------------------------------------
reset()
section("Suppression window renewed on each successful route")

post_route("route-1", suppression_window_seconds=2)

post_alert("a1", service="payment-api")  # routes, sets window to now+2s

print("      (waiting 1s — window still active...)")
time.sleep(1)

post_alert("a2", service="payment-api")   # suppressed (still in window)

print("      (waiting 1s — still within original window...)")
time.sleep(1)

# Window from a1 should have expired (2s elapsed), but it was renewed by... wait
# Actually suppression is only renewed when routing is NOT suppressed.
# a2 was suppressed so it shouldn't renew. a1 set it. After 2s from a1, it should expire.
data = post_alert("a3", service="payment-api")
check("Alert routes again after window expires", data["suppressed"] is False, data.get("suppressed"))


# -------------------------------------------------------------------------
# Suppression window with multiple services — each tracked independently
# -------------------------------------------------------------------------
reset()
section("Multiple services tracked independently on same route")

post_route("route-1", suppression_window_seconds=300)

services = ["payment-api", "auth-service", "orders-api", "user-service"]

# First alert for each service — all should route
for i, svc in enumerate(services):
    data = post_alert(f"first-{svc}", service=svc)
    check(f"First alert for '{svc}' routes normally", data["suppressed"] is False, data.get("suppressed"))

# Second alert for each service — all should be suppressed
for i, svc in enumerate(services):
    data = post_alert(f"second-{svc}", service=svc)
    check(f"Second alert for '{svc}' is suppressed", data["suppressed"] is True, data.get("suppressed"))


# -------------------------------------------------------------------------
# suppression_reason contains a future suppressed_until timestamp
# -------------------------------------------------------------------------
reset()
section("suppression_reason contains suppressed_until timestamp in the future")

from datetime import datetime, timezone

post_route("route-1", suppression_window_seconds=300)
post_alert("a-reason-1", service="payment-api")
suppressed = post_alert("a-reason-2", service="payment-api")

check("Suppressed alert has suppression_reason", suppressed["suppression_reason"] is not None, suppressed.get("suppression_reason"))

# The reason string should contain a timestamp — parse it to confirm it's in the future
reason = suppressed.get("suppression_reason", "")
check("suppression_reason is a non-empty string", isinstance(reason, str) and len(reason) > 0, reason)

# Verify the reason mentions the service and route
check("suppression_reason mentions service name", "payment-api" in reason, reason)
check("suppression_reason mentions route id", "route-1" in reason, reason)

# The suppressed_until time in the reason should be in the future (window is 300s from now)
# Extract an ISO-formatted substring and verify it's parseable and after now
import re
ts_match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", reason)
if ts_match:
    ts_str = ts_match.group(0) + "Z"
    try:
        suppressed_until = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        check("suppressed_until in reason is in the future (wall-clock based)", suppressed_until > now, str(suppressed_until))
    except ValueError:
        check("suppressed_until in reason is parseable", False, ts_str)
else:
    check("suppression_reason contains a timestamp", False, reason)


# -------------------------------------------------------------------------
# Delete route and recreate — suppression window is cleared
# -------------------------------------------------------------------------
reset()
section("Delete route and recreate — suppression window is cleared")

post_route("route-1", suppression_window_seconds=300)
post_alert("a1", service="payment-api")

suppressed = post_alert("a2", service="payment-api")
check("Alert suppressed before route deletion", suppressed["suppressed"] is True, suppressed.get("suppressed"))

requests.delete(f"{BASE_URL}/routes/route-1")
post_route("route-1", suppression_window_seconds=300)

first_after_recreate = post_alert("a3", service="payment-api")
check("First alert after route recreate is NOT suppressed (window cleared on delete)", first_after_recreate["suppressed"] is False, first_after_recreate.get("suppressed"))
check("First alert after recreate routes normally", first_after_recreate["routed_to"] is not None, first_after_recreate.get("routed_to"))


# -------------------------------------------------------------------------
# Suppression expiry uses server wall-clock time, not alert.timestamp
# -------------------------------------------------------------------------
reset()
section("Suppression expiry uses server wall-clock time, not alert.timestamp")

post_route("route-1", suppression_window_seconds=300)

# Open window with a normal alert
first = post_alert("a-clock-1", service="payment-api")
check("First alert routes normally", first["suppressed"] is False, first.get("suppressed"))

# Alert with a timestamp far in the past — suppression should still apply (wall-clock not expired)
past_data = requests.post(f"{BASE_URL}/alerts", json={
    "id": "a-clock-past",
    "severity": "critical",
    "service": "payment-api",
    "group": "backend",
    "timestamp": "2000-01-01T12:00:00Z",
}).json()
check("Alert with old timestamp still suppressed (wall-clock window still active)", past_data["suppressed"] is True, past_data.get("suppressed"))

# Alert with a timestamp far in the future — suppression should still apply
future_data = requests.post(f"{BASE_URL}/alerts", json={
    "id": "a-clock-future",
    "severity": "critical",
    "service": "payment-api",
    "group": "backend",
    "timestamp": "2099-12-31T23:59:00Z",
}).json()
check("Alert with future timestamp still suppressed (wall-clock window still active)", future_data["suppressed"] is True, future_data.get("suppressed"))

# After window expires (2s window), alert with old timestamp should route again
reset()
post_route("route-1", suppression_window_seconds=2)
requests.post(f"{BASE_URL}/alerts", json={
    "id": "a-clock-open",
    "severity": "critical",
    "service": "payment-api",
    "group": "backend",
    "timestamp": "2026-03-25T14:30:00Z",
})
print("      (waiting 3s for 2s suppression window to expire...)")
time.sleep(3)
expired_data = requests.post(f"{BASE_URL}/alerts", json={
    "id": "a-clock-expired",
    "severity": "critical",
    "service": "payment-api",
    "group": "backend",
    "timestamp": "2000-01-01T12:00:00Z",  # old timestamp, but wall-clock window has expired
}).json()
check("Alert routes again after wall-clock window expires (regardless of alert.timestamp)", expired_data["suppressed"] is False, expired_data.get("suppressed"))


# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
total = passed + failed
print(f"\n{'='*50}")
print(f"Section 6 — Suppression Windows: {passed}/{total} passed", "✓" if failed == 0 else "✗")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
