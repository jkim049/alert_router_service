# Notification status values — used across engine, routers, stats, and seed.
# All three outcomes always produce a Notification record.
NOTIFICATION_PENDING = "pending"        # Matched a route and was delivered
NOTIFICATION_SUPPRESSED = "suppressed"  # Matched a route but suppression window was active
NOTIFICATION_UNROUTED = "unrouted"      # No route matched
