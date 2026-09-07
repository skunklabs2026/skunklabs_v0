"""Operator mission commands.

Two endpoints, both intentionally thin: the interlocks live in the mission
state machine, not in the HTTP layer. A route that could authorize an
engagement on its own would be a second, weaker copy of that logic.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.deps import PipelineDep
from backend.schemas import CommandResponse

router = APIRouter(tags=["mission"])


@router.post("/api/authorize", response_model=CommandResponse)
async def authorize(pipeline: PipelineDep) -> CommandResponse:
    """Operator engagement authorization.

    The only action the operator must take during the demo. Rejected unless
    the mission has reached AWAITING_AUTHORIZATION.
    """
    ok, detail = pipeline.authorize()
    return CommandResponse(ok=ok, state=pipeline.mission.state, detail=detail)


@router.post("/api/reset", response_model=CommandResponse)
async def reset(pipeline: PipelineDep) -> CommandResponse:
    """Reset the mission so the full sequence can be demonstrated again."""
    pipeline.reset()
    return CommandResponse(
        ok=True,
        state=pipeline.mission.state,
        detail="Mission reset. Ready for a new run.",
    )
