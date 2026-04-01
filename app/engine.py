"""
Route evaluation logic.

Pure functions only — no database access, no HTTP concerns.
Receives Alert and Route model instances; returns all matching routes sorted by priority desc, id asc.

Routing flow (confirmed):
  1. Evaluate all routes against the alert's conditions.
  2. Collect all matching routes.
  3. If active_hours is set on a route, check whether alert.timestamp falls within the
     active window in the route's specified timezone. If not, exclude the route.
  4. Order matching routes by priority descending.
  5. The highest-priority route wins and produces the notification.
     Tiebreaker: alphabetically lowest route id (deterministic).
  6. Suppression is checked by the caller (requires DB state) — not handled here.

NOTE — concurrency race condition: if two alerts for the same service arrive simultaneously,
both may pass the suppression check before either writes the SuppressionRecord (check-then-act
is not atomic). Acceptable for a single-container test environment.

To harden: add a unique constraint on (route_id, service) in SuppressionRecord and wrap the
suppression check + notification write in a single transaction. With this in place, SQLite
serializes the writes — whichever request acquires the write lock first is routed (notification
created), the other receives an IntegrityError on insert and is recorded as suppressed.
Priority between the two is first-write-wins (lock acquisition order), which is
non-deterministic but safe: exactly one notification is produced, no duplicates.
  7. If no routes match, the caller records the alert as "unrouted".

Active hours: uses alert.timestamp, NOT server time. Format: {"timezone": "America/New_York", "start": "HH:MM", "end": "HH:MM"}.
Overnight windows (start > end) are supported.
"""

import fnmatch
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timezone as dt_timezone
from zoneinfo import ZoneInfo

from app.constants import NOTIFICATION_PENDING, NOTIFICATION_SUPPRESSED, NOTIFICATION_UNROUTED
from app.models import Alert, Route


def _conditions_match(conditions: dict, alert: Alert) -> bool:
    """Return True if the alert satisfies all specified condition fields."""

    severity_filter: list[str] | None = conditions.get("severity")
    if severity_filter is not None:
        if alert.severity not in severity_filter:
            return False

    service_filter: list[str] | None = conditions.get("service")
    if service_filter is not None:
        if not any(fnmatch.fnmatch(alert.service, pattern) for pattern in service_filter):
            return False

    group_filter: list[str] | None = conditions.get("group")
    if group_filter is not None:
        if alert.group not in group_filter:
            return False

    labels_filter: dict[str, str] | None = conditions.get("labels")
    if labels_filter is not None:
        alert_labels: dict = alert.labels or {}
        for key, value in labels_filter.items():
            if alert_labels.get(key) != value:
                return False

    return True


def _is_active(route: Route, alert: Alert) -> bool:
    """
    Return True if the route is active at the time of the alert.
    Uses alert.timestamp (NOT server time) for the check.
    If active_hours is None, the route is always active.

    active_hours format: {"timezone": "America/New_York", "start": "HH:MM", "end": "HH:MM"}

    Handles overnight windows (start > end, e.g. "22:00" to "06:00"):
    - Normal window (start <= end): active if start <= local_time <= end
    - Overnight window (start > end): active if local_time >= start OR local_time <= end
    """
    if route.active_hours is None:
        return True

    tz = ZoneInfo(route.active_hours["timezone"])

    # Ensure timestamp is timezone-aware; treat naive timestamps as UTC
    ts = alert.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt_timezone.utc)

    local_time = ts.astimezone(tz).time()
    start = dt_time.fromisoformat(route.active_hours["start"])
    end = dt_time.fromisoformat(route.active_hours["end"])

    if start <= end:
        return start <= local_time <= end
    else:
        return local_time >= start or local_time <= end


@dataclass
class RoutingResult:
    winner: Route | None
    suppressed: bool
    suppression_applied: bool
    suppression_reason: str | None
    notification_status: str  # "pending" | "suppressed" | "unrouted"


def resolve_winner(
    matched: list[Route],
    active_suppressions: dict[str, datetime],
    service: str,
) -> RoutingResult:
    """
    Walk matched routes in priority order, falling through suppressed ones,
    and return the winning route plus suppression metadata.

    active_suppressions: mapping of route_id -> suppressed_until for routes
    currently within their suppression window for the given service. Built
    by the caller from a single DB query before calling this function.
    """
    winner = None
    suppressed = False
    suppression_applied = False
    suppression_reason = None
    notification_status = NOTIFICATION_UNROUTED

    for candidate in matched:
        suppressed_until = active_suppressions.get(candidate.id)

        if suppressed_until is not None:
            # Candidate is suppressed — record it as fallback and keep looking
            if winner is None:
                winner = candidate
                suppressed = True
                suppression_applied = True
                notification_status = NOTIFICATION_SUPPRESSED
                suppression_reason = (
                    f"Alert for service '{service}' on route '{candidate.id}' "
                    f"suppressed until {suppressed_until.strftime('%Y-%m-%dT%H:%M:%SZ')}"
                )
            continue

        # Found an unsuppressed route — this is the winner
        winner = candidate
        suppressed = False
        suppression_applied = False
        suppression_reason = None
        notification_status = NOTIFICATION_PENDING
        break

    return RoutingResult(
        winner=winner,
        suppressed=suppressed,
        suppression_applied=suppression_applied,
        suppression_reason=suppression_reason,
        notification_status=notification_status,
    )


def evaluate(alert: Alert, routes: list[Route]) -> list[Route]:
    """
    Evaluate an alert against all routes. Returns ALL matching routes sorted by
    priority descending, then id ascending (deterministic tiebreaker).

    The caller is responsible for:
    - Treating matched[0] as the winner (highest priority).
    - Checking suppression on the winner (requires DB state).
    - Recording the notification and suppression record.
    - Building matched_routes and evaluation_details for the response.
    """
    matched: list[Route] = []

    for route in routes:
        if not _conditions_match(route.conditions, alert):
            continue
        if not _is_active(route, alert):
            continue
        matched.append(route)

    return sorted(matched, key=lambda r: (-r.priority, r.id))
