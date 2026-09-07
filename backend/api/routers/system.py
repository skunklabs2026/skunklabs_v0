"""Read-only system endpoints: health, telemetry snapshot, event log.

Live state travels over the WebSocket. These exist so a browser, a curl, or
a monitoring check can read the same values without opening a socket.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.deps import PipelineDep
from backend.schemas import MissionEvent, TelemetryFrame

router = APIRouter(tags=["system"])


@router.get("/api/health")
async def health(pipeline: PipelineDep) -> dict:
    """Liveness plus enough detail to debug a failed demo start."""
    telemetry = pipeline.snapshot()
    return {
        "ok": True,
        "detector": pipeline.detector.name,
        "detector_ready": pipeline.detector.ready,
        "video_source": pipeline.video.describe,
        "sensor_online": pipeline.video.online,
        "state": telemetry.mission.state.value if telemetry else "STARTING",
    }


@router.get("/api/telemetry", response_model=TelemetryFrame | None)
async def telemetry(pipeline: PipelineDep):
    """Current telemetry snapshot. The WebSocket is preferred for live use."""
    return pipeline.snapshot()


@router.get("/api/events", response_model=list[MissionEvent])
async def events(pipeline: PipelineDep):
    """The full retained operator event log."""
    return pipeline.event_log()
