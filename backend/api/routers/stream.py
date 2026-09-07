"""MJPEG preview stream.

MJPEG rather than WebRTC on purpose: it is a handful of lines, has no
negotiation to fail mid-demo, and any browser renders it in a plain <img>.
Overlays are drawn by the frontend from telemetry rather than burned into
these frames, so the UI stays crisp at any window size.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from backend.api.deps import PipelineDep

router = APIRouter(tags=["stream"])

# Boundary token for the multipart MJPEG stream.
BOUNDARY = "skunkframe"


@router.get("/api/video")
async def video_stream(request: Request, pipeline: PipelineDep) -> Response:
    """Stream the processed frames as multipart JPEG."""

    async def frames():
        # Pace the preview at the configured rate; the pipeline may run
        # faster than the display needs.
        interval = 1.0 / max(pipeline.settings.target_fps, 1.0)
        while True:
            if await request.is_disconnected():
                break
            jpeg = pipeline.jpeg()
            if jpeg:
                yield (
                    b"--" + BOUNDARY.encode() + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"
                )
            await asyncio.sleep(interval)

    return StreamingResponse(
        frames(),
        media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )
