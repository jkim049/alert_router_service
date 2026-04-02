# Alert Router Service

A backend service that ingests monitoring alerts, evaluates them against user-defined routing rules, and produces routed notification outputs.

---

## Requirements

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)

No other dependencies need to be installed.

---

## Running the Service

**Start the service:**

```bash
docker compose up --build
```

The service will be available at `http://localhost:8080`.

**Stop the service:**

```bash
docker compose down
```

---

## Exploring the API

Once the service is running, open your browser and go to:

```
http://localhost:8080/docs
```

This opens an interactive API explorer where you can read documentation for every endpoint and make requests directly from the browser — no additional tools required.

---

## API Overview

| Method | Path | Description |
|---|---|---|
| `POST` | `/routes` | Create or update a routing rule |
| `GET` | `/routes` | List all routing rules |
| `DELETE` | `/routes/{id}` | Delete a routing rule |
| `POST` | `/alerts` | Submit an alert and trigger routing |
| `GET` | `/alerts` | List alerts (supports filters) |
| `GET` | `/alerts/{id}` | Get a specific alert and its routing result |
| `GET` | `/stats` | View aggregate routing statistics |
| `POST` | `/test` | Dry-run an alert without recording it |
| `POST` | `/reset` | Clear all data |
| `GET` | `/health` | Health check |

---

## Quick Start Example

**1. Create a routing rule:**

```bash
curl -X POST http://localhost:8080/routes \
  -H "Content-Type: application/json" \
  -d '{
    "id": "route-critical",
    "conditions": { "severity": ["critical"] },
    "target": { "type": "slack", "channel": "#oncall" },
    "priority": 10
  }'
```

**2. Submit an alert:**

```bash
curl -X POST http://localhost:8080/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "id": "alert-001",
    "severity": "critical",
    "service": "payment-api",
    "group": "backend",
    "timestamp": "2026-03-25T14:30:00Z"
  }'
```

**3. Check routing statistics:**

```bash
curl http://localhost:8080/stats
```

---

## Data Persistence

Alert and routing data is stored in a SQLite database at `./data/alerts.db`. This file is created automatically on first run and persists across container restarts.

To start fresh, either run `POST /reset` via the API or delete the `data/` directory and restart the service.

---

## Seed Data

The service starts with an empty database. Use the `/seed` endpoint to load sample data:

```bash
curl -X POST http://localhost:8080/seed
```

Returns `{"seeded": true}` if data was inserted, or `{"seeded": false}` if the database already contains data (safe to call repeatedly).

**Seed routes:**

| ID | Matches | Target | Priority |
|---|---|---|---|
| `route-critical-pagerduty` | `severity: critical` | PagerDuty | 100 |
| `route-payment-slack` | `service: payment-*` | Slack `#payments-oncall` | 50 |
| `route-infra-email` | `group: infrastructure` | Email `ops@example.com` | 30 |
| `route-warnings-webhook` | `severity: warning`, business hours (UTC) | Webhook | 10 |

**Seed alerts** (one of each routing outcome):

| ID | Service | Severity | Outcome |
|---|---|---|---|
| `alert-001` | `payment-api` | critical | Routed → PagerDuty |
| `alert-002` | `payment-api` | critical | Fell through to Slack (PagerDuty suppressed) |
| `alert-003` | `db-primary` | warning | Routed → email |
| `alert-004` | `auth-service` | info | Unrouted (no matching rule) |

**To re-seed after clearing data:**

```bash
curl -X POST http://localhost:8080/reset
curl -X POST http://localhost:8080/seed
```

---

## Running Tests

Tests require Python 3.11+ and the test dependencies installed locally:

```bash
python3 -m venv ~/myenv
source ~/myenv/bin/activate
pip install -r requirements.txt -r requirements-test.txt
pytest tests/ -v
```

---

## OpenAPI Spec

The generated spec is committed at `openapi.json`. To regenerate it after making API changes:

```bash
python3 -m venv ~/myenv          # skip if venv already exists
source ~/myenv/bin/activate
pip install -r requirements.txt  # skip if already installed
python3 -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2))" > openapi.json
```

---

## Routing Rules Reference

### Conditions

All specified fields must match (unspecified fields match everything):

| Field | Type | Behaviour |
|---|---|---|
| `severity` | list of strings | Alert severity must be in the list |
| `service` | list of strings | Alert service must match at least one entry (glob patterns supported, e.g. `"payment-*"`) |
| `group` | list of strings | Alert group must be in the list |
| `labels` | object | Every key-value pair must exist in the alert's labels |

### Target Types

| Type | Required Fields |
|---|---|
| `slack` | `channel` |
| `email` | `address` |
| `pagerduty` | `service_key` |
| `webhook` | `url` (optional: `headers`) |

### Active Hours

Routes can be restricted to a time window using `active_hours`:

```json
{
  "timezone": "America/New_York",
  "start": "09:00",
  "end": "17:00"
}
```

Matching uses the alert's `timestamp`, not server time.

---

## Design Decisions

These are the ambiguous points where the spec left room for interpretation, and the explicit choices made for each.

### Multi-route match: highest priority wins, one notification per alert

When multiple routes match an alert, only one notification is produced — the highest-priority route wins. Routes with equal priority are broken by alphabetical route ID, which is deterministic regardless of insertion order.

**Why**: Producing one notification per matching route would cause duplicate pages/messages for every alert that matches more than one rule, which is the common case in layered alerting setups.

### Suppression fallthrough

When the highest-priority matching route is suppressed, routing falls through to the next-highest match rather than suppressing the alert entirely.

**Why**: Suppression windows are typically set to prevent a noisy channel (e.g. PagerDuty) from firing repeatedly. A lower-priority passive channel (e.g. Slack) on a separate route has its own suppression state — silencing the top route should not hide the alert from all other routes. If every matching route is suppressed, the alert is recorded as suppressed against the highest-priority one.

### Suppression key is `(route_id, service)`, not `(route_id, alert_id)`

Suppression is scoped per service per route, not per individual alert.

**Why**: The intent of a suppression window is "don't fire this channel repeatedly for the same failing service." Two different alert IDs from the same service are the same real-world problem, so both should be covered by the window once it is set.

### Suppression window uses server time, not alert timestamp

The suppression window start and end are calculated from `datetime.utcnow()` at the moment the alert is processed, not from the alert's own `timestamp`.

**Why**: Alert timestamps are client-provided and can be stale (e.g. a delayed delivery from a monitoring agent). Using the server clock ensures the window reflects real wall-clock time from when the notification was actually sent.

### Active hours use alert timestamp, not server time

The opposite choice from suppression: `active_hours` windows are evaluated against the alert's own `timestamp`.

**Why**: Active hours represent "only notify me if this alert happened during business hours." The relevant time is when the event occurred, not when it arrived at the router. A delayed alert from 10:00 should still be treated as a business-hours alert even if it arrives at 18:00.

### Alert re-submission (same ID) updates the record and re-evaluates routing

POSTing an alert with an ID that already exists updates the existing alert record and creates a new notification from a fresh routing evaluation.

**Why**: Monitoring systems often re-emit the same alert periodically while a problem is ongoing. Re-evaluation ensures the latest route configuration applies, and the updated record is retrievable via `GET /alerts/{id}` with the most recent result.

### `total_alerts_processed` counts processing events, not unique alerts

The `total_alerts_processed` stat in `GET /stats` counts every routing evaluation performed, including re-submissions of the same alert ID. Re-submitting `alert-001` three times counts as three processing events.

**Why**: Each submission runs the full routing pipeline and produces a new notification record. The stat reflects how much work the system has done, not how many distinct problems were reported. To count unique alerts, use the number of distinct alert IDs visible in `GET /alerts`.

### Notifications are stored records, not deliveries

No actual messages are sent to Slack, PagerDuty, email, or webhooks. A notification is a database record of "this alert was matched to this route."

**Why**: Keeps the service self-contained and testable without external dependencies. All routing outcomes are observable via the API regardless of whether the downstream channel is reachable.

### Validation errors return 400 with `{"error": "..."}`, not 422

FastAPI's default for malformed request bodies is HTTP 422 with a structured Pydantic error object. This service overrides that to return 400 with a plain `{"error": "message"}` body.

**Why**: 422 with nested Pydantic error arrays is correct for machine clients but noisy for humans exploring the API via `/docs` or `curl`. A flat `{"error": "..."}` string is immediately readable without parsing.
