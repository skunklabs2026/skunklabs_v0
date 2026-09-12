"""V0 defense scenario: state, operator commands, and the live feed.

Thin on purpose. Interlocks - "authorize only a response whose node is READY"
- live in `backend/scenario/simulation.py`; a rejected command surfaces here
as a 409 carrying the state machine's own explanation.
"""

from __future__ import annotations

import contextlib
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from backend.api.deps import ScenarioDep
from backend.api.models import (
    AuthorizeScenarioRequest,
    ConfigureScenarioRequest,
    ReassignResponseRequest,
)
from backend.scenario import ScenarioService
from backend.scenario.models import ScenarioCommandResult, ScenarioSnapshot

log = logging.getLogger(__name__)

router = APIRouter(tags=["scenario"])

# An idle scenario publishes nothing; resend the snapshot this often anyway so
# the UI can tell a quiet backend from a dead one.
HEARTBEAT_S = 1.0


def _checked(result: ScenarioCommandResult) -> ScenarioCommandResult:
    if not result.ok:
        raise HTTPException(status_code=409, detail=result.detail)
    return result


@router.get("/api/scenario", response_model=ScenarioSnapshot)
async def scenario_state(service: ScenarioDep) -> ScenarioSnapshot:
    return service.snapshot


@router.post("/api/scenario/configure", response_model=ScenarioCommandResult)
async def configure(
    service: ScenarioDep, body: ConfigureScenarioRequest
) -> ScenarioCommandResult:
    """Select the threat scenario and/or centre the site on a location. IDLE only."""
    return _checked(
        await service.configure(
            scenario_id=body.scenario_id, latitude=body.latitude, longitude=body.longitude
        )
    )


@router.post("/api/scenario/start", response_model=ScenarioCommandResult)
async def start(service: ScenarioDep) -> ScenarioCommandResult:
    """START DEMO with the configured scenario."""
    return _checked(await service.start())


@router.post(
    "/api/scenario/responses/{engagement_id}/authorize", response_model=ScenarioCommandResult
)
async def authorize(
    engagement_id: str, service: ScenarioDep, body: AuthorizeScenarioRequest | None = None
) -> ScenarioCommandResult:
    """AUTHORIZE SIMULATION for one response, with the proposed or a chosen count."""
    count = body.interceptors if body else None
    return _checked(await service.authorize(engagement_id, count))


@router.post(
    "/api/scenario/responses/{engagement_id}/decline", response_model=ScenarioCommandResult
)
async def decline(engagement_id: str, service: ScenarioDep) -> ScenarioCommandResult:
    """Decline one proposed response."""
    return _checked(await service.decline(engagement_id))


@router.post(
    "/api/scenario/responses/{engagement_id}/reassign", response_model=ScenarioCommandResult
)
async def reassign(
    engagement_id: str, service: ScenarioDep, body: ReassignResponseRequest
) -> ScenarioCommandResult:
    """Give one proposed response to a different node, chosen by the operator."""
    return _checked(await service.reassign(engagement_id, body.node_id))


@router.post("/api/scenario/reset", response_model=ScenarioCommandResult)
async def reset(service: ScenarioDep) -> ScenarioCommandResult:
    """RESET DEMO. Keeps the selected scenario and location."""
    return _checked(await service.reset())


@router.websocket("/ws/scenario")
async def scenario_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    service: ScenarioService = websocket.app.state.scenario
    version = -1
    try:
        while True:
            version, snapshot = await service.wait_for_update(version, HEARTBEAT_S)
            await websocket.send_json(snapshot.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("Scenario socket failed")
        with contextlib.suppress(Exception):
            await websocket.close()
