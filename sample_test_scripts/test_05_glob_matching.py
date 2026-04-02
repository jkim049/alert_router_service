#!/usr/bin/env python3
"""
Section 5: Glob Matching on Service Field
Covers:
  - Common patterns: payment-*, auth-*, *-api
  - Prefix, suffix, and contains patterns
  - Non-matching service names
  - Multiple patterns in service list (OR semantics)
  - Exact string match alongside globs
  - Edge cases: *, ?, character ranges
  - Case sensitivity
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


def post_route(id, service_patterns, priority=10):
    requests.post(f"{BASE_URL}/routes", json={
        "id": id,
        "conditions": {"service": service_patterns},
        "target": {"type": "slack", "channel": f"#{id}"},
        "priority": priority,
    })


def post_alert(service, id="alert-1"):
    return requests.post(f"{BASE_URL}/alerts", json={
        "id": id,
        "severity": "critical",
        "service": service,
        "group": "backend",
        "timestamp": "2026-03-25T14:30:00Z",
    }).json()


def routed(data):
    return data["routed_to"] is not None


# -------------------------------------------------------------------------
# Prefix glob: payment-*
# -------------------------------------------------------------------------
reset()
section("Prefix glob: payment-*")

post_route("route-1", ["payment-*"])

matching = ["payment-api", "payment-worker", "payment-service", "payment-processor", "payment-"]
for svc in matching:
    data = post_alert(service=svc, id=f"a-{svc}")
    check(f"payment-* matches '{svc}'", routed(data), data.get("routed_to"))

non_matching = ["auth-api", "user-service", "payment", "PAYMENT-api", "PAYMENt-api", "xpayment-api"]
for svc in non_matching:
    data = post_alert(service=svc, id=f"a-{svc}")
    check(f"payment-* does not match '{svc}'", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Prefix glob: auth-*
# -------------------------------------------------------------------------
reset()
section("Prefix glob: auth-*")

post_route("route-1", ["auth-*"])

matching = ["auth-service", "auth-api", "auth-worker", "auth-v2", "auth-"]
for svc in matching:
    data = post_alert(service=svc, id=f"a-{svc}")
    check(f"auth-* matches '{svc}'", routed(data), data.get("routed_to"))

non_matching = ["payment-api", "oauth-service", "auth", "AUTH-service", "reauth-service"]
for svc in non_matching:
    data = post_alert(service=svc, id=f"a-{svc}")
    check(f"auth-* does not match '{svc}'", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Suffix glob: *-api
# -------------------------------------------------------------------------
reset()
section("Suffix glob: *-api")

post_route("route-1", ["*-api"])

matching = ["payment-api", "auth-api", "user-api", "orders-api", "-api"]
for svc in matching:
    data = post_alert(service=svc, id=f"a-{svc}")
    check(f"*-api matches '{svc}'", routed(data), data.get("routed_to"))

non_matching = ["payment-worker", "auth-service", "api", "payment-api-v2", "payment-API"]
for svc in non_matching:
    data = post_alert(service=svc, id=f"a-{svc}")
    check(f"*-api does not match '{svc}'", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Contains glob: *payment*
# -------------------------------------------------------------------------
reset()
section("Contains glob: *payment*")

post_route("route-1", ["*payment*"])

matching = ["payment-api", "payment-worker", "xpayment-api", "api-payment", "new-payment-service"]
for svc in matching:
    data = post_alert(service=svc, id=f"a-{svc}")
    check(f"*payment* matches '{svc}'", routed(data), data.get("routed_to"))

non_matching = ["auth-service", "user-api", "PAYMENT-api"]
for svc in non_matching:
    data = post_alert(service=svc, id=f"a-{svc}")
    check(f"*payment* does not match '{svc}'", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Wildcard *: matches everything
# -------------------------------------------------------------------------
reset()
section("Wildcard * matches all services")

post_route("route-1", ["*"])

for svc in ["payment-api", "auth-service", "anything", "x", "123", "a-b-c-d"]:
    data = post_alert(service=svc, id=f"a-{svc}")
    check(f"* matches '{svc}'", routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Single character glob: ?
# -------------------------------------------------------------------------
reset()
section("Single character glob: ?")

post_route("route-1", ["pay?ent-api"])

data = post_alert(service="payment-api", id="a1")
check("pay?ent-api matches 'payment-api'", routed(data), data.get("routed_to"))

data = post_alert(service="payent-api", id="a2")
check("pay?ent-api does not match 'payent-api' (0 chars)", not routed(data), data.get("routed_to"))

data = post_alert(service="payyment-api", id="a3")
check("pay?ent-api does not match 'payyment-api' (2 chars)", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Multiple patterns — OR semantics
# -------------------------------------------------------------------------
reset()
section("Multiple service patterns — OR semantics (any match)")

post_route("route-1", ["payment-*", "auth-*", "*-api"])

matching = [
    ("payment-worker", "matches payment-*"),
    ("auth-service", "matches auth-*"),
    ("user-api", "matches *-api"),
    ("payment-api", "matches payment-* and *-api"),
    ("auth-api", "matches auth-* and *-api"),
]
for svc, reason in matching:
    data = post_alert(service=svc, id=f"a-{svc}")
    check(f"'{svc}' matches ({reason})", routed(data), data.get("routed_to"))

non_matching = ["user-service", "orders-worker", "db-primary"]
for svc in non_matching:
    data = post_alert(service=svc, id=f"a-{svc}")
    check(f"'{svc}' does not match any pattern", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Exact string match (no glob characters)
# -------------------------------------------------------------------------
reset()
section("Exact string match (no glob characters)")

post_route("route-1", ["payment-api"])

data = post_alert(service="payment-api", id="a1")
check("Exact match routes", routed(data), data.get("routed_to"))

data = post_alert(service="payment-api-v2", id="a2")
check("Superset of exact match does not route", not routed(data), data.get("routed_to"))

data = post_alert(service="payment", id="a3")
check("Subset of exact match does not route", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Exact match and glob in same list
# -------------------------------------------------------------------------
reset()
section("Exact match and glob combined in same list")

post_route("route-1", ["payment-api", "auth-*"])

data = post_alert(service="payment-api", id="a1")
check("Exact 'payment-api' matches", routed(data), data.get("routed_to"))

data = post_alert(service="payment-worker", id="a2")
check("'payment-worker' does not match (exact only, no glob)", not routed(data), data.get("routed_to"))

data = post_alert(service="auth-service", id="a3")
check("'auth-service' matches via glob", routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Case sensitivity
# -------------------------------------------------------------------------
reset()
section("Case sensitivity")

post_route("route-1", ["payment-*"])

for svc in ["PAYMENT-api", "Payment-api", "PAYMENT-API", "pAyMeNt-api"]:
    data = post_alert(service=svc, id=f"a-{svc.lower()}")
    check(f"payment-* is case-sensitive, does not match '{svc}'", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Multi-segment and special character patterns
# -------------------------------------------------------------------------
reset()
section("Multi-segment and hyphenated patterns")

post_route("route-1", ["*-*"])

matching = ["payment-api", "auth-service", "a-b", "x-y-z"]
for svc in matching:
    data = post_alert(service=svc, id=f"a-{svc}")
    check(f"*-* matches '{svc}'", routed(data), data.get("routed_to"))

non_matching = ["paymentapi", "authservice", "single"]
for svc in non_matching:
    data = post_alert(service=svc, id=f"a-{svc}")
    check(f"*-* does not match '{svc}'", not routed(data), data.get("routed_to"))


# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
total = passed + failed
print(f"\n{'='*50}")
print(f"Section 5 — Glob Matching: {passed}/{total} passed", "✓" if failed == 0 else "✗")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
