"""REST routers, one per role.

    system.py   health, telemetry snapshot, event log
    mission.py  operator authorize / reset
    source.py   video library, uploads, camera and detector selection
    stream.py   MJPEG preview

`api_router` aggregates them, so `main.py` includes one router and the
ordering of the rest is decided here.
"""

from fastapi import APIRouter

from backend.api.routers import mission, source, stream, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(mission.router)
api_router.include_router(source.router)
api_router.include_router(stream.router)

__all__ = ["api_router"]
