"""The V0 scenario API contract.

Sent whole, as one `ScenarioSnapshot`, on every change: over `/ws/scenario`
while the demo runs and in the response to every command. The UI keeps
exactly one copy of it, so the map and the launcher view cannot disagree.

Mirrored to `frontend/src/scenario/contract.ts` by `scripts/gen_types.py`.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel


class MissionState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAULT = "FAULT"


class NodeState(str, Enum):
    STANDBY = "STANDBY"
    TRACK_RECEIVED = "TRACK_RECEIVED"
    ORIENTING = "ORIENTING"
    READY = "READY"
    AUTHORIZED = "AUTHORIZED"
    SIMULATED_LAUNCH = "SIMULATED_LAUNCH"


class TrackStatus(str, Enum):
    INBOUND = "INBOUND"
    # Both terminal states are simulation outcomes, not assessments.
    INTERCEPTED = "INTERCEPTED"
    REACHED_SITE = "REACHED_SITE"


class EngagementStatus(str, Enum):
    # Node assigned and orienting.
    PROPOSED = "PROPOSED"
    # Node READY; the operator decides.
    AWAITING_AUTHORIZATION = "AWAITING_AUTHORIZATION"
    AUTHORIZED = "AUTHORIZED"
    IN_FLIGHT = "IN_FLIGHT"
    INTERCEPTED = "INTERCEPTED"
    DECLINED = "DECLINED"
    # The threat reached the site before this response resolved.
    ABORTED = "ABORTED"


class InterceptorStatus(str, Enum):
    # Authorized, waiting its turn in the salvo.
    PENDING = "PENDING"
    IN_FLIGHT = "IN_FLIGHT"
    # This interceptor reached the threat.
    INTERCEPT = "INTERCEPT"
    # Another interceptor reached it first, or it reached the site.
    STOOD_DOWN = "STOOD_DOWN"


class LocationSource(str, Enum):
    # The operator's device reported its position.
    DEVICE = "DEVICE"
    # No device position yet; the configured fallback.
    DEFAULT = "DEFAULT"


class GeoPoint(BaseModel):
    latitude: float
    longitude: float


class ScenarioOption(BaseModel):
    id: str
    name: str
    description: str
    threat_count: int


class ProtectedSite(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    protected_radius_km: float
    location_source: LocationSource


class DefenseNode(BaseModel):
    id: str
    latitude: float
    longitude: float
    coverage_radius_km: float
    current_yaw_deg: float
    target_yaw_deg: float
    current_pitch_deg: float
    target_pitch_deg: float
    state: NodeState
    # The response this node is working, if any.
    engagement_id: str | None
    inventory: int
    inventory_capacity: int


class Track(BaseModel):
    id: str
    latitude: float
    longitude: float
    altitude_m: float
    heading_deg: float
    speed_kmh: float
    status: TrackStatus
    # Which TrackSource produced it - "SIMULATED" in V0.
    source: str
    site_distance_km: float
    inside_protected_area: bool
    # The latest response for this threat, if one was ever proposed.
    engagement_id: str | None
    trail: list[GeoPoint]


class Engagement(BaseModel):
    """A proposed response: one node against one threat."""

    id: str
    node_id: str
    track_id: str
    status: EngagementStatus
    # What the system proposes; the operator may authorize a different count.
    proposed_interceptors: int
    # The threat as seen from the node, for orientation displays.
    range_km: float
    bearing_deg: float
    elevation_deg: float
    interceptor_ids: list[str]
    intercept_point: GeoPoint | None


class SimulatedInterceptor(BaseModel):
    id: str
    node_id: str
    track_id: str
    engagement_id: str
    latitude: float
    longitude: float
    heading_deg: float
    state: InterceptorStatus
    trail: list[GeoPoint]


class ScenarioEvent(BaseModel):
    """One operator log line. `timestamp` is epoch seconds."""

    timestamp: float
    message: str


class ScenarioSnapshot(BaseModel):
    type: Literal["scenario"] = "scenario"
    # Publish counter. The same state reaches the UI by two paths (command
    # response and WebSocket); the UI keeps whichever copy is newest.
    revision: int = 0
    state: MissionState
    scenario_id: str
    scenarios: list[ScenarioOption]
    # True from START DEMO until COMPLETE or FAULT.
    running: bool
    # Wall seconds since START DEMO.
    elapsed_s: float
    # World-time multiplier applied to threat and interceptor motion.
    time_scale: float
    site: ProtectedSite
    nodes: list[DefenseNode]
    tracks: list[Track]
    engagements: list[Engagement]
    interceptors: list[SimulatedInterceptor]
    # Responses awaiting an operator decision, in the order to present them.
    decision_queue: list[str]
    # Derived here so the UI never re-implements an interlock.
    can_start: bool
    can_configure: bool
    fault: str | None
    events: list[ScenarioEvent]


class ScenarioCommandResult(BaseModel):
    ok: bool
    detail: str
    snapshot: ScenarioSnapshot
