"""The mission pipeline.

Split by role, so a change to one concern touches one file:

    hub.py         shared state between the worker thread and the API
    inputs.py      which video source and detector are live
    perception.py  pixels -> tracks
    engagement.py  tracks -> mission decisions
    runtime.py     the frame loop that wires them together

`MissionPipeline` is the only name the API layer needs.
"""

from backend.pipeline.engagement import EngagementResult, EngagementStage
from backend.pipeline.hub import TelemetryHub
from backend.pipeline.inputs import InputController
from backend.pipeline.perception import PerceptionStage
from backend.pipeline.runtime import MissionPipeline

__all__ = [
    "EngagementResult",
    "EngagementStage",
    "InputController",
    "MissionPipeline",
    "PerceptionStage",
    "TelemetryHub",
]
