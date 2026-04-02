#!/usr/bin/env python3
"""
Section 7: Active Hours & Timezones
Covers:
  - Alerts inside active window are matched
  - Alerts outside active window are not matched
  - America/New_York timezone conversion (UTC offset applied correctly)
  - Boundary times: exactly at start (inclusive), exactly at end (exclusive)
  - Overnight windows (start > end, e.g. 22:00–06:00)
  - Route without active_hours always matches
  - Fallback to lower-priority route when higher is inactive
  - Active hours uses alert.timestamp, not server time
  - Multiple timezones
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


def post_route(id, active_hours=None, priority=10, conditions=None):
    payload = {
        "id": id,
        "conditions": conditions or {},
        "target": {"type": "slack", "channel": f"#{id}"},
        "priority": priority,
    }
    if active_hours:
        payload["active_hours"] = active_hours
    requests.post(f"{BASE_URL}/routes", json=payload)


def post_alert(id, timestamp, service="payment-api", severity="critical"):
    return requests.post(f"{BASE_URL}/alerts", json={
        "id": id,
        "severity": severity,
        "service": service,
        "group": "backend",
        "timestamp": timestamp,
    }).json()


def routed_to(data, route_id):
    return data["routed_to"] is not None and data["routed_to"]["route_id"] == route_id


def routed(data):
    return data["routed_to"] is not None


# -------------------------------------------------------------------------
# No active_hours — always matches
# -------------------------------------------------------------------------
reset()
section("No active_hours — always matches regardless of timestamp")

post_route("route-always")

for ts in [
    "2026-03-25T00:00:00Z",
    "2026-03-25T06:00:00Z",
    "2026-03-25T12:00:00Z",
    "2026-03-25T17:00:00Z",
    "2026-03-25T23:59:00Z",
]:
    data = post_alert(f"a-{ts[-9:-1]}", timestamp=ts)
    check(f"No active_hours matches at {ts[-9:-4]}", routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# UTC window: 09:00–17:00
# -------------------------------------------------------------------------
reset()
section("UTC window 09:00–17:00")

post_route("route-1", active_hours={"timezone": "UTC", "start": "09:00", "end": "17:00"})

inside = [
    ("2026-03-25T09:00:00Z", "exactly at start (inclusive)"),
    ("2026-03-25T09:01:00Z", "just after start"),
    ("2026-03-25T12:00:00Z", "midday"),
    ("2026-03-25T14:30:00Z", "mid-afternoon"),
    ("2026-03-25T16:59:59Z", "one second before end"),
]
for ts, desc in inside:
    data = post_alert(f"a-in-{ts[11:16]}", timestamp=ts)
    check(f"Inside window ({desc})", routed(data), data.get("routed_to"))

outside = [
    ("2026-03-25T08:59:59Z", "one second before start"),
    ("2026-03-25T17:00:00Z", "exactly at end (exclusive)"),
    ("2026-03-25T17:00:01Z", "just after end"),
    ("2026-03-25T20:00:00Z", "evening"),
    ("2026-03-25T00:00:00Z", "midnight"),
]
for ts, desc in outside:
    data = post_alert(f"a-out-{ts[11:16]}", timestamp=ts)
    check(f"Outside window ({desc})", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# America/New_York — UTC-4 in summer (EDT), UTC-5 in winter (EST)
# -------------------------------------------------------------------------
reset()
section("America/New_York 09:00–17:00 (UTC-4 in summer = EDT)")

# 2026-03-25 is after DST switch (second Sunday in March = March 8, 2026), so UTC-4
post_route("route-1", active_hours={"timezone": "America/New_York", "start": "09:00", "end": "17:00"})

# 09:00 EDT = 13:00 UTC
# 17:00 EDT = 21:00 UTC
inside_utc = [
    ("2026-03-25T13:00:00Z", "09:00 NY = 13:00 UTC (start, inclusive)"),
    ("2026-03-25T15:00:00Z", "11:00 NY = 15:00 UTC"),
    ("2026-03-25T20:00:00Z", "16:00 NY = 20:00 UTC"),
    ("2026-03-25T20:59:59Z", "16:59:59 NY = 20:59:59 UTC (just before end)"),
]
for ts, desc in inside_utc:
    data = post_alert(f"a-ny-in-{ts[11:16]}", timestamp=ts)
    check(f"Inside NY window ({desc})", routed(data), data.get("routed_to"))

outside_utc = [
    ("2026-03-25T12:59:59Z", "08:59:59 NY = 12:59:59 UTC (before start)"),
    ("2026-03-25T21:00:00Z", "17:00 NY = 21:00 UTC (end, exclusive)"),
    ("2026-03-25T21:00:01Z", "17:00:01 NY = 21:00:01 UTC (after end)"),
    ("2026-03-25T02:00:00Z", "22:00 prev day NY = 02:00 UTC (overnight)"),
]
for ts, desc in outside_utc:
    data = post_alert(f"a-ny-out-{ts[11:16]}", timestamp=ts)
    check(f"Outside NY window ({desc})", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# America/New_York — winter (EST = UTC-5)
# -------------------------------------------------------------------------
reset()
section("America/New_York 09:00–17:00 (UTC-5 in winter = EST)")

# 2026-01-15 is in winter, EST = UTC-5
post_route("route-1", active_hours={"timezone": "America/New_York", "start": "09:00", "end": "17:00"})

# 09:00 EST = 14:00 UTC
# 17:00 EST = 22:00 UTC
inside_utc = [
    ("2026-01-15T14:00:00Z", "09:00 NY = 14:00 UTC (start, inclusive)"),
    ("2026-01-15T18:00:00Z", "13:00 NY = 18:00 UTC"),
    ("2026-01-15T21:59:59Z", "16:59:59 NY = 21:59:59 UTC (just before end)"),
]
for ts, desc in inside_utc:
    data = post_alert(f"a-est-in-{ts[11:16]}", timestamp=ts)
    check(f"Inside EST window ({desc})", routed(data), data.get("routed_to"))

outside_utc = [
    ("2026-01-15T13:59:59Z", "08:59:59 NY = 13:59:59 UTC (before start)"),
    ("2026-01-15T22:00:00Z", "17:00 NY = 22:00 UTC (end, exclusive)"),
]
for ts, desc in outside_utc:
    data = post_alert(f"a-est-out-{ts[11:16]}", timestamp=ts)
    check(f"Outside EST window ({desc})", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Overnight window: 22:00–06:00 UTC
# -------------------------------------------------------------------------
reset()
section("Overnight window 22:00–06:00 UTC")

post_route("route-1", active_hours={"timezone": "UTC", "start": "22:00", "end": "06:00"})

inside = [
    ("2026-03-25T22:00:00Z", "exactly at start (inclusive)"),
    ("2026-03-25T23:00:00Z", "before midnight"),
    ("2026-03-25T00:00:00Z", "midnight"),
    ("2026-03-25T03:00:00Z", "early morning"),
    ("2026-03-25T05:59:59Z", "one second before end"),
]
for ts, desc in inside:
    data = post_alert(f"a-night-{ts[11:16]}", timestamp=ts)
    check(f"Inside overnight window ({desc})", routed(data), data.get("routed_to"))

outside = [
    ("2026-03-25T06:00:00Z", "exactly at end (exclusive)"),
    ("2026-03-25T06:00:01Z", "just after end"),
    ("2026-03-25T12:00:00Z", "midday"),
    ("2026-03-25T21:59:59Z", "one second before start"),
]
for ts, desc in outside:
    data = post_alert(f"a-night-out-{ts[11:16]}", timestamp=ts)
    check(f"Outside overnight window ({desc})", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Active hours uses alert.timestamp, not server time
# -------------------------------------------------------------------------
reset()
section("Active hours uses alert.timestamp (not server time)")

# Window that is definitely NOT active right now (server time),
# but the alert timestamp is inside the window
post_route("route-1", active_hours={"timezone": "UTC", "start": "09:00", "end": "17:00"})

# Old timestamp clearly within window — should match regardless of current server time
data = post_alert("a1", timestamp="2020-01-15T12:00:00Z")
check("Old timestamp inside window routes (uses alert.timestamp)", routed(data), data.get("routed_to"))

# Old timestamp clearly outside window
data = post_alert("a2", timestamp="2020-01-15T20:00:00Z")
check("Old timestamp outside window does not route", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Fallback: inactive high-priority route falls through to always-active lower route
# -------------------------------------------------------------------------
reset()
section("Fallback to lower-priority route when higher is outside active hours")

# High priority route — active only 09:00–17:00 UTC
post_route("route-business", active_hours={"timezone": "UTC", "start": "09:00", "end": "17:00"}, priority=20)
# Low priority route — always active (no active_hours)
post_route("route-always", priority=5)

# Timestamp inside business hours — high priority wins
data = post_alert("a1", timestamp="2026-03-25T12:00:00Z")
check("Inside business hours: high-priority route wins", routed_to(data, "route-business"), data.get("routed_to"))

# Timestamp outside business hours — falls through to always-active route
data = post_alert("a2", timestamp="2026-03-25T20:00:00Z")
check("Outside business hours: falls through to always-active route", routed_to(data, "route-always"), data.get("routed_to"))
check("Outside business hours: not suppressed (just inactive)", data["suppressed"] is False, data.get("suppressed"))


# -------------------------------------------------------------------------
# Multiple timezones
# -------------------------------------------------------------------------
reset()
section("Multiple timezones")

# Europe/London = UTC+1 in summer (BST), UTC+0 in winter
post_route("route-london", active_hours={"timezone": "Europe/London", "start": "09:00", "end": "17:00"})

# 2026-07-01 is summer BST = UTC+1
# 09:00 BST = 08:00 UTC, 17:00 BST = 16:00 UTC
data = post_alert("a-bst-in", timestamp="2026-07-01T10:00:00Z")  # 11:00 BST
check("Europe/London BST: 11:00 BST inside 09:00–17:00", routed(data), data.get("routed_to"))

data = post_alert("a-bst-out", timestamp="2026-07-01T17:00:00Z")  # 18:00 BST
check("Europe/London BST: 18:00 BST outside 09:00–17:00", not routed(data), data.get("routed_to"))

reset()
# Asia/Tokyo = UTC+9 (no DST)
post_route("route-tokyo", active_hours={"timezone": "Asia/Tokyo", "start": "09:00", "end": "17:00"})

# 09:00 JST = 00:00 UTC, 17:00 JST = 08:00 UTC
data = post_alert("a-jst-in", timestamp="2026-03-25T03:00:00Z")   # 12:00 JST
check("Asia/Tokyo: 12:00 JST inside 09:00–17:00", routed(data), data.get("routed_to"))

data = post_alert("a-jst-out", timestamp="2026-03-25T10:00:00Z")  # 19:00 JST
check("Asia/Tokyo: 19:00 JST outside 09:00–17:00", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# evaluation_details counts with active_hours excluded routes
# -------------------------------------------------------------------------
reset()
section("evaluation_details counts routes excluded by active_hours as not_matched")

# route-business: condition matches all, but active only 09:00–17:00 UTC
# route-always: no active_hours, always matches, lower priority
post_route("route-business", active_hours={"timezone": "UTC", "start": "09:00", "end": "17:00"}, priority=20)
post_route("route-always", priority=5)

# Alert outside business hours — route-business condition-matches but active_hours excludes it
data = post_alert("a-eval-out", timestamp="2026-03-25T20:00:00Z")
details = data.get("evaluation_details", {})
check("total_routes_evaluated is 2", details.get("total_routes_evaluated") == 2, details)
check("routes_matched is 1 (only route-always)", details.get("routes_matched") == 1, details)
check("routes_not_matched is 1 (route-business excluded by active_hours)", details.get("routes_not_matched") == 1, details)
check("route-business not in matched_routes", "route-business" not in data.get("matched_routes", []), data.get("matched_routes"))
check("route-always in matched_routes", "route-always" in data.get("matched_routes", []), data.get("matched_routes"))
check("invariant: matched + not_matched == total",
      details.get("routes_matched", 0) + details.get("routes_not_matched", 0) == details.get("total_routes_evaluated", -1),
      details)

# Alert inside business hours — both routes match
data = post_alert("a-eval-in", timestamp="2026-03-25T12:00:00Z")
details = data.get("evaluation_details", {})
check("total_routes_evaluated is 2 (inside hours)", details.get("total_routes_evaluated") == 2, details)
check("routes_matched is 2 (both active)", details.get("routes_matched") == 2, details)
check("routes_not_matched is 0 (both active)", details.get("routes_not_matched") == 0, details)
check("route-business wins (higher priority)", data["routed_to"]["route_id"] == "route-business", data.get("routed_to"))

# Three routes: two excluded by active_hours, one always-on
reset()
post_route("route-morning", active_hours={"timezone": "UTC", "start": "06:00", "end": "12:00"}, priority=30)
post_route("route-afternoon", active_hours={"timezone": "UTC", "start": "12:00", "end": "18:00"}, priority=20)
post_route("route-always", priority=5)

# Alert at 20:00 UTC — both time-gated routes excluded
data = post_alert("a-eval-evening", timestamp="2026-03-25T20:00:00Z")
details = data.get("evaluation_details", {})
check("total_routes_evaluated is 3", details.get("total_routes_evaluated") == 3, details)
check("routes_matched is 1 (only catch-all)", details.get("routes_matched") == 1, details)
check("routes_not_matched is 2 (both time-gated excluded)", details.get("routes_not_matched") == 2, details)
check("invariant holds for 3-route case",
      details.get("routes_matched", 0) + details.get("routes_not_matched", 0) == details.get("total_routes_evaluated", -1),
      details)


# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
total = passed + failed
print(f"\n{'='*50}")
print(f"Section 7 — Active Hours & Timezones: {passed}/{total} passed", "✓" if failed == 0 else "✗")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
