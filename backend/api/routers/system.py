"""Read-only system endpoints: health, telemetry snapshot, event log.

Live state travels over the WebSocket. These exist so a browser, a curl, or
a monitoring check can read the same values without opening a socket.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from backend.api.deps import PipelineDep, ScenarioDep
from backend.schemas import MissionEvent, TelemetryFrame

router = APIRouter(tags=["system"])


@router.get("/api/health")
async def health(request: Request, scenario: ScenarioDep) -> dict:
    """Liveness plus enough detail to debug a failed demo start."""
    body: dict = {
        "ok": True,
        "mission_state": scenario.snapshot.state.value,
        "video_pipeline": request.app.state.pipeline is not None,
    }
    pipeline = request.app.state.pipeline
    if pipeline is not None:
        telemetry = pipeline.snapshot()
        body.update(
            detector=pipeline.detector.name,
            detector_ready=pipeline.detector.ready,
            video_source=pipeline.video.describe,
            sensor_online=pipeline.video.online,
            state=telemetry.mission.state.value if telemetry else "STARTING",
        )
    return body


@router.get("/api/telemetry", response_model=TelemetryFrame | None)
async def telemetry(pipeline: PipelineDep):
    """Current telemetry snapshot. The WebSocket is preferred for live use."""
    return pipeline.snapshot()


@router.get("/api/events", response_model=list[MissionEvent])
async def events(pipeline: PipelineDep):
    """The full retained operator event log."""
    return pipeline.event_log()
