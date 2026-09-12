"""WebSocket telemetry channel.

Pushes one `TelemetryFrame` per processed frame. The client never polls and
never computes mission state - it renders what arrives.

The pipeline's frame loop is blocking (OpenCV, inference), so waiting for the
next frame is offloaded to a thread executor rather than blocking the event
loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.pipeline import MissionPipeline

log = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/telemetry")
async def telemetry_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    pipeline: MissionPipeline | None = websocket.app.state.pipeline
    if pipeline is None:
        # 1013 "try again later": the sensor lab is off in this process.
        await websocket.close(code=1013, reason="Video pipeline disabled")
        return
    log.info("Operator UI connected")

    # Send the retained event log once on connect so a client that joins mid-
    # run - or reconnects after a drop - sees the full history rather than
    # only events from this point forward.
    try:
        await websocket.send_json(
            {
                "type": "history",
                "events": [e.model_dump(mode="json") for e in pipeline.event_log()],
            }
        )
    except Exception:
        return

    loop = asyncio.get_running_loop()
    sequence = -1

    try:
        while True:
            sequence, telemetry = await loop.run_in_executor(
                None, pipeline.wait_for_frame, sequence, 1.0
            )
            if telemetry is None:
                # Pipeline has not produced a frame yet; keep the socket warm.
                await asyncio.sleep(0.05)
                continue
            await websocket.send_json(telemetry.model_dump(mode="json", by_alias=True))
    except WebSocketDisconnect:
        log.info("Operator UI disconnected")
    except Exception:
        log.exception("Telemetry socket failed")
        # The socket may already be gone; closing is best-effort.
        with contextlib.suppress(Exception):
            await websocket.close()
