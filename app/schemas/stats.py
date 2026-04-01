from pydantic import BaseModel


class RouteStats(BaseModel):
    total_matched: int
    total_routed: int
    total_suppressed: int


class StatsResponse(BaseModel):
    total_alerts_processed: int
    total_routed: int
    total_suppressed: int
    total_unrouted: int
    by_severity: dict[str, int]
    by_route: dict[str, RouteStats]
    by_service: dict[str, int]
