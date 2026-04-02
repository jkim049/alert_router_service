# Alert Router Service — Claude Context

## Project Overview

A backend service that ingests monitoring alerts via a REST API, evaluates them against user-defined routing rules, and produces routed notification outputs. Runs in a single Docker container. Target audience includes non-technical users — ease of setup and discoverability are first-class concerns.

---

## Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Database**: SQLite (via SQLAlchemy ORM)
- **Validation**: Pydantic v2
- **Server**: Uvicorn
- **Container**: Docker + docker-compose

---

## Architectural Patterns

### Layered Structure
Each file has one responsibility. Do not mix concerns across layers:

| Layer | File(s) | Responsibility |
|---|---|---|
| Transport | `routers/` | Route definitions, request/response handling only |
| Assembly | `main.py` | App instance, lifespan, exception handler, router includes |
| Schema | `schemas/` | Pydantic models for all request bodies and responses |
| ORM | `models/` | SQLAlchemy table definitions only — no business logic |
| Data access | `database.py` | Engine, session factory, `get_db` dependency, `utcnow()` |
| Business logic | `evaluator.py` | Rule evaluation — pure logic, no DB calls, no HTTP concerns |
| Seeding | `seed.py` | Sample data insertion, runs once on empty DB at startup |

### Dependency Injection for DB Sessions
All database access goes through FastAPI's `Depends(get_db)` pattern. Never instantiate a session manually inside a route.

```python
# correct
def get_alerts(db: Session = Depends(get_db)):
    ...

# wrong — do not do this
def get_alerts():
    db = SessionLocal()
    ...
```

### Rule Evaluation is Pure
`engine.py` receives plain Python objects (not DB models, not HTTP request objects). It returns a list of matched rules. All DB reads and writes happen in `main.py` before and after calling the engine.

### Seed on Empty DB
`seed.py` is called at app startup. It checks if any data exists before inserting — never truncates or re-seeds a populated database.

---

## Coding Conventions

### General
- Use **type hints on all function signatures** — parameters and return types
- Use **f-strings** for string formatting, not `.format()` or `%`
- Keep route handlers thin — delegate logic to `engine.py` or helper functions
- No inline SQL — all queries go through SQLAlchemy ORM

### Naming
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions and variables: `snake_case`
- Pydantic schema classes: suffix with `Create`, `Update`, `Response` as appropriate (e.g., `AlertCreate`, `AlertResponse`)
- SQLAlchemy model classes: plain noun, no suffix (e.g., `Alert`, `RoutingRule`, `Notification`)

### FastAPI Routes
- Group related routes together in `main.py` with a comment header (e.g., `# --- Alerts ---`)
- Always specify `response_model` on every route
- Always specify `status_code` explicitly (e.g., `status_code=201` for POST)
- Use `HTTPException` with meaningful `detail` strings for all error responses

### Pydantic Schemas
- All response schemas include `id` and `created_at`
- Use `model_config = ConfigDict(from_attributes=True)` on response schemas to support ORM mapping
- Request schemas (Create/Update) never include `id` or `created_at`

### SQLAlchemy Models
- All models inherit from a shared `Base` (defined in `database.py`)
- Every model has: `id` (Integer, primary key, autoincrement), `created_at` (DateTime, default=utcnow)
- JSON columns (e.g., `conditions`, `labels`) use `Column(JSON)`

---

## API Conventions

- **IDs**: Sequential integers — never UUIDs or random values
- **Ordering**: All list endpoints return results ordered by `id ASC`
- **HTTP status codes**:
  - `200` — successful GET or DELETE
  - `201` — successful POST (resource created)
  - `404` — resource not found
  - `422` — validation error (FastAPI default for bad request bodies)
- **All responses are JSON** — no 204 No Content, every endpoint returns a JSON body
- **Response envelope**: No wrapper objects — return the resource or list directly
  ```json
  // correct
  [{"id": 1, "name": "..."}, {"id": 2, "name": "..."}]

  // wrong
  {"data": [...], "count": 2}
  ```
- **Timestamps**: Always UTC, always ISO 8601 format

---

## Confirmed API Endpoints

| Method | Path | Status |
|---|---|---|
| POST | `/routes` | Implemented |
| GET | `/routes` | Implemented |
| DELETE | `/routes/{id}` | Implemented |
| POST | `/alerts` | Implemented |
| GET | `/alerts` | Implemented — query params: `service`, `severity`, `routed`, `suppressed` |
| GET | `/alerts/{id}` | Implemented |
| GET | `/stats` | Implemented |
| POST | `/test` | Implemented — dry-run, reads suppression state but writes nothing |
| POST | `/reset` | Implemented — clears all tables, returns {"status": "ok"} |
| POST | `/seed` | Implemented — inserts sample data if DB is empty, returns {"seeded": bool} |

No other endpoints exist. Do not add `GET /alerts`, `GET /notifications`, or any unlisted endpoint.

## Key Design Decisions

- **Notifications are stored records**, not actual deliveries. No real Slack/email/webhook calls. A notification is a persisted record of "alert X matched rule Y → route to channel Z", retrievable via `GET /notifications`.
- **`docker compose up` is the only command needed** to build and run the service. No other steps.
- **`seed.py` runs automatically on startup** — detects an empty database and inserts sample data. Uses SQLAlchemy models, never raw SQL, to avoid schema drift.
- **FastAPI `/docs`** (Swagger UI) must remain available — it is the primary interface for non-technical users.
- **No authentication** — the API is open.

---

## Guardrails — Do Not Do These

- Do not add a separate database container (Postgres, MySQL, etc.) — SQLite only
- Do not use raw SQL strings anywhere — ORM only
- Do not perform actual notification delivery (no HTTP calls to external services, no email, no Slack)
- Do not return UUIDs or random identifiers — sequential integer IDs only
- Do not wrap list responses in an envelope object
- Do not use `status_code=204` — every endpoint returns a JSON body
- Do not skip `response_model` on any route
- Do not instantiate `SessionLocal` directly inside route handlers
- Do not put business logic (rule evaluation) inside route handlers or ORM models
- Do not re-seed the database if it already contains data
- Do not use `datetime.now()` or `datetime.utcnow()` — always use `datetime.now(timezone.utc).replace(tzinfo=None)` for naive UTC datetimes
- Do not use `alert.timestamp` for suppression window calculations — use server time (`datetime.now(timezone.utc)`)

---

## Non-Obvious Constraints

These are things an evaluator or test suite is likely to probe. Keep them in mind when making any implementation decision.

- **"Deterministic" means more than just correct** — same input must always produce the same response shape, same ordering, same structure. No random IDs, no unordered sets, no floats where ints are expected.
- **Rule evaluation order is the most likely test target** — if 3 rules match one alert, what happens is the core question of the service. Do not implement this without a confirmed answer to the open question below.
- **Notifications are records, not side effects** — the test suite can only assert against HTTP responses. If notifications aren't stored and retrievable, they don't exist as far as tests are concerned.
- **Rule condition expressiveness matters** — an equality-only condition system will likely fail tests that check severity ranges or label subsets. Support at minimum: `eq`, `neq`, `in`, `contains`.
- **Alert fields vs. labels distinction** — most alerting systems use fixed top-level fields (`name`, `severity`, `source`) plus an arbitrary `labels` map. Rule conditions must be able to match on both. A rule that only matches top-level fields is incomplete.
- **Idempotency of alert submission** — a test may POST the same alert twice. The current decision is to create two separate records (no deduplication). If this changes, update this file.
- **The `/docs` UI is a non-technical user's primary interface** — any endpoint that is missing a `response_model`, has a vague description, or returns an unexpected shape will be confusing and may fail contract tests.

---

## Alert Schema (confirmed)

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Client-provided. Used as upsert key — re-submitting same ID updates the existing alert |
| `severity` | string enum | yes | One of: `critical`, `warning`, `info` |
| `service` | string | yes | Originating service name |
| `group` | string | yes | Logical grouping (e.g. `backend`, `frontend`, `infrastructure`) |
| `description` | string | no | Human-readable description |
| `timestamp` | string (ISO 8601) | yes | Client-provided, parsed to datetime |
| `labels` | object | no | Arbitrary key-value string pairs |

**Do not use**: `name`, `source`, `message`, `status` — these were placeholders before the schema was confirmed.

## Route Schema (confirmed)

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Client-provided, upsert key |
| `conditions` | object | yes | Matching criteria — format not yet confirmed (see open questions) |
| `target` | object | yes | `{type: slack\|email\|pagerduty\|webhook, ...type-specific fields}` |
| `priority` | integer | yes | Higher = higher priority |
| `suppression_window_seconds` | integer | no | Default 0. Suppresses duplicate alerts for same `service` on this route within the window |
| `active_hours` | object | no | If absent, route is always active. Format not yet confirmed |

**Multi-match behavior (confirmed):** Highest priority wins — one notification per alert. Alphabetical `id` is the deterministic tiebreaker on equal priority.

**Suppression key:** `(route_id, service)` pair. Tracked in `SuppressionRecord` table with a `suppressed_until` datetime.
**Suppression window timing:** Uses server time (`datetime.now(timezone.utc)`), not `alert.timestamp`.
**Alert re-submission (same id):** Updates the existing alert record AND re-evaluates routing. A new `Notification` record is always created as a result.

## Routing Flow (confirmed, 7 steps)

Every POST /alerts triggers this sequence:

1. Evaluate all routes' conditions against the alert.
2. Collect all matching routes.
3. For each matching route with `active_hours` set, check whether `alert.timestamp` falls within the active window (in the route's timezone). Exclude routes that are inactive. **Uses alert.timestamp, not server time.**
4. Order remaining matches by priority descending.
5. Highest-priority match wins. Alphabetical `id` breaks ties deterministically.
6. If the winning route has a `suppression_window_seconds > 0`, check `SuppressionRecord` for a `(route_id, service)` pair with a `suppressed_until` in the future. If suppressed: record a `Notification` with `status = "suppressed"`, update the suppression record, produce no further output.
7. If no routes matched: record a `Notification` with `status = "unrouted"` and `route_id = null`.

## Notification Statuses

All three outcomes create a `Notification` record — all are observable via `GET /notifications`.

| Status | `route_id` | `channel` | Meaning |
|---|---|---|---|
| `pending` | set | set | Successfully routed; notification queued |
| `suppressed` | set | set | Winning route matched but suppression window active |
| `unrouted` | `null` | `null` | No routes matched the alert |

**Do not use**: `name` on routes — it was a placeholder and is not in the confirmed spec.

### Matching Rules (confirmed)

Conditions is a structured object — NOT a list of `{field, op, value}` dicts. Do not use `RuleCondition`.

```json
{
  "severity": ["critical", "warning"],
  "service": ["payment-*", "auth-service"],
  "group": ["backend"],
  "labels": {"env": "prod"}
}
```

- **ALL** specified fields must match (AND semantics).
- **Omitted fields** match everything (wildcard — do not filter).
- `severity`: alert.severity must be **in** the list.
- `service`: alert.service must match **at least one** entry; glob patterns supported (`fnmatch`).
- `group`: alert.group must be **in** the list.
- `labels`: every k/v pair must exist in alert.labels (**subset** match — alert may have extra labels).

### Route Target Types

Implemented as a Pydantic discriminated union on `target.type`. Stored as JSON in the DB.

| type | Required fields | Optional fields |
|---|---|---|
| `slack` | `channel` (string) | — |
| `email` | `address` (string) | — |
| `pagerduty` | `service_key` (string) | — |
| `webhook` | `url` (string) | `headers` (object of string key-value pairs, default `{}`) |

## Open Questions (unresolved — do not make assumptions, ask first)

- ~~**Conditions / Matching Rules format**~~ — resolved. See Matching Rules below.
- ~~**Target type-specific fields**~~ — resolved. See Route Target Types below.
- ~~**`active_hours` object format**~~ — resolved. See below.
- **Timezone library**: `zoneinfo` (Python 3.11+ stdlib) + `tzdata` pip package. Do not use `pytz` or `dateutil`.

### Active Hours (confirmed)

```json
{ "timezone": "America/New_York", "start": "09:00", "end": "17:00" }
```

- `timezone`: IANA timezone name
- `start` / `end`: 24-hour `"HH:MM"` strings
- Checks `alert.timestamp`, not server time. Naive timestamps treated as UTC.
- Overnight windows (`start > end`, e.g. `"22:00"` to `"06:00"`) are supported.
- **Suppression fallthrough**: if the winning route is suppressed, does routing fall through to the next-highest match, or is it suppressed entirely (no notification)?
- **`name` field on routes**: include or drop? Not present in the confirmed spec.
- **DELETE /routes response shape**: `{"id": "...", "deleted": true}` or same as POST `{"id": "...", "created": bool}`? Currently returning 200 with shape TBD.
- **GET /routes/{id}**: single-item GET endpoint needed, or list only?
- **Suppression fallthrough**: pending.

---

## File Structure

```
flow_interview/
  app/
    __init__.py           # empty package marker
    main.py               # FastAPI app, lifespan, exception handler, router includes
    database.py           # engine, SessionLocal, Base, get_db, utcnow()
    evaluator.py          # rule evaluation — pure functions, no DB/HTTP
    seed.py               # seed_db() — inserts sample data on empty DB at startup
    models/
      __init__.py         # re-exports Alert, Route, Notification, SuppressionRecord
      alert.py            # Alert ORM model
      route.py            # Route ORM model
      notification.py     # Notification ORM model
      suppression.py      # SuppressionRecord ORM model
    schemas/
      __init__.py         # re-exports all schemas
      alerts.py           # AlertCreate, AlertIngestResponse, AlertListResponse, ...
      routes.py           # RouteUpsert, RouteResponse, RouteConditions, ActiveHours, targets
      stats.py            # StatsResponse, RouteStats
    routers/
      __init__.py
      alerts.py           # POST /alerts, GET /alerts, GET /alerts/{id}
      routes.py           # POST /routes, GET /routes, DELETE /routes/{id}
      stats.py            # GET /stats
      dry_run.py          # POST /test (dry-run, no side effects)
      system.py           # GET /health, POST /reset, POST /seed
  data/                   # SQLite DB lives here (mounted as Docker volume)
  Dockerfile
  docker-compose.yml
  requirements.txt
  tests/
    __init__.py
    conftest.py           # client fixture (in-memory SQLite + StaticPool) + payload factories
    test_routing.py       # core routing logic: priority, suppression, conditions, active hours
    test_api.py           # API contracts, validation errors, other endpoints
  README.md
  PLAN.md
  CLAUDE.md
```
