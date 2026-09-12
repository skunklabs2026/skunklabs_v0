"""Request bodies for the REST API.

Response models live in `backend.schemas` - they are shared with the
WebSocket and the generated TypeScript types. These are inbound only.

Field-level validation here is deliberately thin. Where a value has a
domain rule with an operator-readable explanation - which detectors exist,
which paths are loadable - the rule lives with the component that owns it
and surfaces as a 400 carrying that message, rather than as a 422 carrying
a schema dump the console cannot usefully display.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConfigureScenarioRequest(BaseModel):
    """Threat scenario and/or the operator's location. Omitted fields are unchanged."""

    scenario_id: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class AuthorizeScenarioRequest(BaseModel):
    """Simulated interceptors the operator commits to one response."""

    # Omitted: the proposed count. The upper bound is the node's inventory,
    # checked by the scenario so the rejection can say how many are available.
    interceptors: int | None = Field(default=None, ge=1)


class ReassignResponseRequest(BaseModel):
    """The node the operator wants to answer this threat instead."""

    node_id: str = Field(min_length=1)


class SelectVideoRequest(BaseModel):
    """Load a specific local video file."""

    path: str = Field(min_length=1)


class SelectCameraRequest(BaseModel):
    camera_index: int = Field(default=0, ge=0, le=15)


class SelectDetectorRequest(BaseModel):
    # Validated by the pipeline, which owns the list of available detectors
    # and returns a message naming them.
    detector: str


class ThresholdRequest(BaseModel):
    # Clamped by the detector rather than rejected here: dragging a slider
    # slightly past its end should retune, not error.
    threshold: float
