"""Input selection: video library, uploads, camera and detector choice.

These routes validate and translate. The filesystem work belongs to
`VideoLibrary`, and applying a change belongs to the pipeline's worker
thread — this module only maps their outcomes onto HTTP status codes.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from backend.api.deps import PipelineDep
from backend.api.models import (
    SelectCameraRequest,
    SelectDetectorRequest,
    SelectVideoRequest,
    ThresholdRequest,
)
from backend.schemas import CommandResponse, SourceStatus
from backend.video.library import UploadTooLarge

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/source", tags=["source"])

UPLOAD_CHUNK_BYTES = 1024 * 1024


@router.get("", response_model=SourceStatus)
async def source_status(pipeline: PipelineDep) -> SourceStatus:
    """Current input configuration and the local video library."""
    return pipeline.source_status()


@router.post("/video", response_model=CommandResponse)
async def select_video(pipeline: PipelineDep, body: SelectVideoRequest) -> CommandResponse:
    """Switch to a video file already on this machine.

    Accepts any absolute local path, so footage does not have to be copied
    into the repository to be tested.
    """
    try:
        path = pipeline.library.resolve(body.path)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    detail = pipeline.use_video_file(path)
    return CommandResponse(ok=True, state=pipeline.mission.state, detail=detail)


@router.post("/camera", response_model=CommandResponse)
async def select_camera(pipeline: PipelineDep, body: SelectCameraRequest) -> CommandResponse:
    detail = pipeline.use_camera(body.camera_index)
    return CommandResponse(ok=True, state=pipeline.mission.state, detail=detail)


@router.post("/detector", response_model=CommandResponse)
async def select_detector(
    pipeline: PipelineDep, body: SelectDetectorRequest
) -> CommandResponse:
    """Swap the detector at runtime, to compare models on the same footage."""
    try:
        detail = pipeline.use_detector(body.detector)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return CommandResponse(ok=True, state=pipeline.mission.state, detail=detail)


@router.post("/threshold", response_model=CommandResponse)
async def set_threshold(pipeline: PipelineDep, body: ThresholdRequest) -> CommandResponse:
    """Retune detector confidence live, without reloading the source."""
    applied = pipeline.set_detection_threshold(body.threshold)
    return CommandResponse(
        ok=True,
        state=pipeline.mission.state,
        detail=f"Detection threshold set to {applied:.2f}.",
    )


@router.post("/upload", response_model=CommandResponse)
async def upload_video(pipeline: PipelineDep, file: UploadFile = File(...)) -> CommandResponse:
    """Accept a video uploaded from the operator's machine and load it."""

    async def chunks():
        while chunk := await file.read(UPLOAD_CHUNK_BYTES):
            yield chunk

    try:
        destination, written = await pipeline.library.save_upload(
            file.filename or "upload.mp4", chunks()
        )
    except UploadTooLarge as exc:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        log.exception("Upload failed")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Upload failed: {exc}"
        ) from exc
    finally:
        await file.close()

    detail = pipeline.use_video_file(destination)
    return CommandResponse(
        ok=True,
        state=pipeline.mission.state,
        detail=f"Uploaded {destination.name} ({written / 1e6:.0f} MB). {detail}",
    )


@router.delete("/upload/{name}", response_model=CommandResponse)
async def delete_upload(pipeline: PipelineDep, name: str) -> CommandResponse:
    """Remove a previously uploaded clip."""
    try:
        target = pipeline.library.resolve_upload(name)
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    # Deleting the clip that is currently playing would strand the pipeline
    # on a file that no longer exists.
    current = pipeline.source_status().active_video
    if current and Path(current).resolve() == target.resolve():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "That clip is currently loaded. Select another source first.",
        )

    target.unlink()
    return CommandResponse(
        ok=True, state=pipeline.mission.state, detail=f"Deleted {target.name}."
    )
