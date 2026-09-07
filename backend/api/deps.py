"""Shared FastAPI dependencies.

The pipeline is created once in the app lifespan and stored on `app.state`.
Every route reaches it through `PipelineDep` rather than touching
`request.app.state` directly, so a route signature says what it needs and a
test can override it in one place.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from backend.config.settings import Settings, get_settings
from backend.pipeline import MissionPipeline


def get_pipeline(request: Request) -> MissionPipeline:
    return request.app.state.pipeline


PipelineDep = Annotated[MissionPipeline, Depends(get_pipeline)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
