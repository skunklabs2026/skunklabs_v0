"""Shared FastAPI dependencies.

The scenario service and the (optional) pipeline are created once in the app
lifespan and stored on `app.state`. Every route reaches them through
`ScenarioDep` / `PipelineDep` rather than touching `request.app.state`
directly, so a route signature says what it needs and a test can override it
in one place.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from backend.config.settings import Settings, get_settings
from backend.pipeline import MissionPipeline
from backend.scenario import ScenarioService


def get_pipeline(request: Request) -> MissionPipeline:
    pipeline = request.app.state.pipeline
    if pipeline is None:
        raise HTTPException(
            status_code=503,
            detail="Video pipeline disabled. Start the backend with "
            "SKUNK_VIDEO_PIPELINE_ENABLED=true to use the sensor lab.",
        )
    return pipeline


def get_scenario(request: Request) -> ScenarioService:
    return request.app.state.scenario


PipelineDep = Annotated[MissionPipeline, Depends(get_pipeline)]
ScenarioDep = Annotated[ScenarioService, Depends(get_scenario)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
