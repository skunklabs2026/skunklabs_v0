"""REST routers, one per role.

    scenario.py  V0 launcher scenario: state, start / authorize / reset, live feed
    system.py    health, telemetry snapshot, event log
    mission.py   video-pipeline operator authorize / reset (sensor lab)
    source.py    video library, uploads, camera and detector selection
    stream.py    MJPEG preview

`api_router` aggregates them, so `main.py` includes one router and the
ordering of the rest is decided here.
"""

from fastapi import APIRouter

from backend.api.routers import mission, scenario, source, stream, system

api_router = APIRouter()
api_router.include_router(scenario.router)
api_router.include_router(system.router)
api_router.include_router(mission.router)
api_router.include_router(source.router)
api_router.include_router(stream.router)

__all__ = ["api_router"]
