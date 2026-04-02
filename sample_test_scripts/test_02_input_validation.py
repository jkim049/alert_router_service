#!/usr/bin/env python3
"""
Section 2: Input Validation
Covers validation errors for both POST /alerts and POST /routes:
  - Missing required fields
  - Invalid severity values
  - Bad timestamps
  - Invalid target types
  - Negative suppression windows
  - Invalid timezones
  - Malformed time formats
All validation errors must return 400 with {"error": "..."} body.
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


def valid_alert(**overrides):
    base = {
        "id": "alert-1",
        "severity": "critical",
        "service": "payment-api",
        "group": "backend",
        "timestamp": "2026-03-25T14:30:00Z",
    }
    base.update(overrides)
    return base


def valid_route(**overrides):
    base = {
        "id": "route-1",
        "conditions": {},
        "target": {"type": "slack", "channel": "#oncall"},
        "priority": 10,
    }
    base.update(overrides)
    return base


# -------------------------------------------------------------------------
# Alert validation — missing required fields
# -------------------------------------------------------------------------
reset()
section("Alert — missing required fields")

for field in ["id", "severity", "service", "group", "timestamp"]:
    payload = valid_alert()
    del payload[field]
    r = requests.post(f"{BASE_URL}/alerts", json=payload)
    check(f"Missing alert '{field}' returns 400", r.status_code == 400, r.status_code)
    check(f"Missing alert '{field}' returns error body", "error" in r.json(), r.json())


# -------------------------------------------------------------------------
# Alert validation — invalid severity
# -------------------------------------------------------------------------
reset()
section("Alert — invalid severity values")

for bad_severity in ["extreme", "CRITICAL", "Critical", "warn", "information", "", "null", 123]:
    payload = valid_alert(severity=bad_severity)
    r = requests.post(f"{BASE_URL}/alerts", json=payload)
    check(f"Invalid severity '{bad_severity}' returns 400", r.status_code == 400, r.status_code)

for good_severity in ["critical", "warning", "info"]:
    payload = valid_alert(id=f"alert-{good_severity}", severity=good_severity)
    r = requests.post(f"{BASE_URL}/alerts", json=payload)
    check(f"Valid severity '{good_severity}' accepted", r.status_code == 200, r.status_code)


# -------------------------------------------------------------------------
# Alert validation — bad timestamps
# -------------------------------------------------------------------------
reset()
section("Alert — bad timestamps")

bad_timestamps = [
    ("25-03-2026", "DD-MM-YYYY format"),
    ("2026/03/25", "slash-separated date"),
    ("not-a-date", "arbitrary string"),
    ("2026-03-25", "date only, no time"),
    ("14:30:00", "time only, no date"),
    ("", "empty string"),
    ("2026-13-01T00:00:00Z", "invalid month 13"),
    ("2026-03-32T00:00:00Z", "invalid day 32"),
]

for ts, description in bad_timestamps:
    r = requests.post(f"{BASE_URL}/alerts", json=valid_alert(timestamp=ts))
    check(f"Bad timestamp ({description}) returns 400", r.status_code == 400, r.status_code)

good_timestamps = [
    ("2026-03-25T14:30:00Z", "UTC Z suffix"),
    ("2026-03-25T14:30:00+00:00", "UTC +00:00 offset"),
    ("2026-03-25T14:30:00+05:30", "positive offset"),
    ("2026-03-25T14:30:00-08:00", "negative offset"),
    ("2026-03-25T00:00:00Z", "midnight UTC"),
]

for ts, description in good_timestamps:
    r = requests.post(f"{BASE_URL}/alerts", json=valid_alert(id=f"alert-ts", timestamp=ts))
    check(f"Valid timestamp ({description}) accepted", r.status_code == 200, r.status_code)


# -------------------------------------------------------------------------
# Route validation — missing required fields
# -------------------------------------------------------------------------
reset()
section("Route — missing required fields")

for field in ["id", "conditions", "target", "priority"]:
    payload = valid_route()
    del payload[field]
    r = requests.post(f"{BASE_URL}/routes", json=payload)
    check(f"Missing route '{field}' returns 400", r.status_code == 400, r.status_code)
    check(f"Missing route '{field}' returns error body", "error" in r.json(), r.json())


# -------------------------------------------------------------------------
# Route validation — invalid target types
# -------------------------------------------------------------------------
reset()
section("Route — invalid target types")

for bad_type in ["telegram", "sms", "teams", "discord", "", "SLACK", "Slack"]:
    r = requests.post(f"{BASE_URL}/routes", json=valid_route(
        target={"type": bad_type, "channel": "#oncall"}
    ))
    check(f"Invalid target type '{bad_type}' returns 400", r.status_code == 400, r.status_code)

# Missing type field entirely
r = requests.post(f"{BASE_URL}/routes", json=valid_route(
    target={"channel": "#oncall"}
))
check("Target with no 'type' field returns 400", r.status_code == 400, r.status_code)

# Valid types all accepted
for target in [
    {"type": "slack", "channel": "#oncall"},
    {"type": "email", "address": "ops@example.com"},
    {"type": "pagerduty", "service_key": "pd-key"},
    {"type": "webhook", "url": "https://hooks.example.com"},
]:
    r = requests.post(f"{BASE_URL}/routes", json=valid_route(
        id=f"route-{target['type']}", target=target
    ))
    check(f"Valid target type '{target['type']}' accepted", r.status_code == 200, r.status_code)


# -------------------------------------------------------------------------
# Route validation — missing target-specific required fields
# -------------------------------------------------------------------------
reset()
section("Route — missing target-specific fields")

r = requests.post(f"{BASE_URL}/routes", json=valid_route(target={"type": "slack"}))
check("Slack missing 'channel' returns 400", r.status_code == 400, r.status_code)

r = requests.post(f"{BASE_URL}/routes", json=valid_route(target={"type": "email"}))
check("Email missing 'address' returns 400", r.status_code == 400, r.status_code)

r = requests.post(f"{BASE_URL}/routes", json=valid_route(target={"type": "pagerduty"}))
check("PagerDuty missing 'service_key' returns 400", r.status_code == 400, r.status_code)

r = requests.post(f"{BASE_URL}/routes", json=valid_route(target={"type": "webhook"}))
check("Webhook missing 'url' returns 400", r.status_code == 400, r.status_code)


# -------------------------------------------------------------------------
# Route validation — suppression window
# -------------------------------------------------------------------------
reset()
section("Route — suppression window validation")

for bad_window in [-1, -100, -9999]:
    r = requests.post(f"{BASE_URL}/routes", json=valid_route(suppression_window_seconds=bad_window))
    check(f"suppression_window_seconds={bad_window} returns 400", r.status_code == 400, r.status_code)

for good_window in [0, 1, 60, 300, 86400]:
    r = requests.post(f"{BASE_URL}/routes", json=valid_route(
        id=f"route-sw-{good_window}",
        suppression_window_seconds=good_window,
    ))
    check(f"suppression_window_seconds={good_window} accepted", r.status_code == 200, r.status_code)


# -------------------------------------------------------------------------
# Route validation — invalid timezones
# -------------------------------------------------------------------------
reset()
section("Route — invalid timezones")

bad_timezones = [
    "Not/ATimezone",
    "America/NotACity",
    "GMT+5",             # non-standard form
    "",
    "random string",
]

for tz in bad_timezones:
    r = requests.post(f"{BASE_URL}/routes", json=valid_route(
        active_hours={"timezone": tz, "start": "09:00", "end": "17:00"}
    ))
    check(f"Invalid timezone '{tz}' returns 400", r.status_code == 400, r.status_code)

good_timezones = [
    "UTC",
    "America/New_York",
    "Europe/London",
    "Asia/Tokyo",
    "Australia/Sydney",
]

for tz in good_timezones:
    r = requests.post(f"{BASE_URL}/routes", json=valid_route(
        id=f"route-tz",
        active_hours={"timezone": tz, "start": "09:00", "end": "17:00"}
    ))
    check(f"Valid timezone '{tz}' accepted", r.status_code == 200, r.status_code)


# -------------------------------------------------------------------------
# Route validation — malformed time formats
# -------------------------------------------------------------------------
reset()
section("Route — malformed time formats")

bad_times = [
    ("9:00", "17:00", "missing leading zero on start"),
    ("09:00", "5:00", "missing leading zero on end"),
    ("9:0", "17:00", "missing leading zero on both parts of start"),
    ("09:00", "17:0", "missing leading zero on minutes of end"),
    ("24:00", "17:00", "invalid hour 24 on start"),
    ("09:00", "25:00", "invalid hour 25 on end"),
    ("09:60", "17:00", "invalid minutes 60 on start"),
    ("09:00", "17:60", "invalid minutes 60 on end"),
    ("09-00", "17:00", "hyphen separator on start"),
    ("09:00", "17-00", "hyphen separator on end"),
    ("9am", "5pm", "am/pm format"),
    ("", "17:00", "empty start"),
    ("09:00", "", "empty end"),
]

for start, end, description in bad_times:
    r = requests.post(f"{BASE_URL}/routes", json=valid_route(
        active_hours={"timezone": "UTC", "start": start, "end": end}
    ))
    check(f"Bad time format ({description}) returns 400", r.status_code == 400, r.status_code)

good_times = [
    ("00:00", "23:59", "midnight to end of day"),
    ("09:00", "17:00", "standard business hours"),
    ("22:00", "06:00", "overnight window"),
    ("00:00", "00:00", "zero-length window"),
]

for start, end, description in good_times:
    r = requests.post(f"{BASE_URL}/routes", json=valid_route(
        id="route-time",
        active_hours={"timezone": "UTC", "start": start, "end": end}
    ))
    check(f"Valid time format ({description}) accepted", r.status_code == 200, r.status_code)


# -------------------------------------------------------------------------
# Invalid submissions must not persist partial records
# -------------------------------------------------------------------------
reset()
section("Invalid submissions do not persist partial records")

# Submit a series of invalid alerts — none should appear in GET /alerts
bad_alert_payloads = [
    {**valid_alert(), "severity": "extreme"},          # bad severity
    {**valid_alert(), "timestamp": "not-a-date"},      # bad timestamp
    {k: v for k, v in valid_alert().items() if k != "id"},  # missing id
    {k: v for k, v in valid_alert().items() if k != "service"},  # missing service
]
for payload in bad_alert_payloads:
    requests.post(f"{BASE_URL}/alerts", json=payload)

r = requests.get(f"{BASE_URL}/alerts").json()
check("No partial alert records after invalid POSTs", r["total"] == 0, r.get("total"))
check("Alerts list is empty after only invalid POSTs", r["alerts"] == [], r.get("alerts"))

s = requests.get(f"{BASE_URL}/stats").json()
check("Stats not incremented by invalid alert submissions", s["total_alerts_processed"] == 0, s.get("total_alerts_processed"))

# Submit a series of invalid routes — none should appear in GET /routes
bad_route_payloads = [
    {**valid_route(), "target": {"type": "telegram", "channel": "#x"}},  # bad target type
    {**valid_route(), "suppression_window_seconds": -1},                  # negative window
    {**valid_route(), "active_hours": {"timezone": "Fake/Zone", "start": "09:00", "end": "17:00"}},  # bad tz
    {k: v for k, v in valid_route().items() if k != "priority"},         # missing priority
]
for payload in bad_route_payloads:
    requests.post(f"{BASE_URL}/routes", json=payload)

r = requests.get(f"{BASE_URL}/routes").json()
check("No partial route records after invalid POSTs", r == [], r)


# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
total = passed + failed
print(f"\n{'='*50}")
print(f"Section 2 — Input Validation: {passed}/{total} passed", "✓" if failed == 0 else "✗")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
