"""Runs the scenario on the asyncio event loop and publishes snapshots.

Everything - the tick, operator commands, WebSocket readers - runs on the one
event loop, so the scenario is never touched from two threads and needs no
lock. Each change produces exactly one new `ScenarioSnapshot`; readers wait
on a version number and always receive the latest whole state, never a diff
they could apply out of order.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable

from backend.scenario.models import ScenarioCommandResult, ScenarioSnapshot
from backend.scenario.simulation import CommandOutcome, DefenseScenario

log = logging.getLogger(__name__)


class ScenarioService:
    def __init__(self, scenario: DefenseScenario) -> None:
        self.scenario = scenario
        self._version = 0
        self._snapshot = scenario.snapshot()
        self._changed = asyncio.Condition()

    @property
    def snapshot(self) -> ScenarioSnapshot:
        return self._snapshot

    async def run(self) -> None:
        """Tick forever at the configured rate. Cancel the task to stop."""
        period = 1.0 / self.scenario.config.timing.tick_hz
        loop = asyncio.get_running_loop()
        last = loop.time()
        while True:
            await asyncio.sleep(period)
            now = loop.time()
            await self.tick(now - last)
            last = now

    async def tick(self, dt: float) -> None:
        try:
            changed = self.scenario.step(dt)
        except Exception:
            # Fail visibly into FAULT rather than killing the tick task and
            # leaving the UI showing a frozen, plausible-looking state.
            log.exception("Scenario step failed")
            self.scenario.fail("simulation error (see backend log)")
            changed = True
        if changed:
            await self._publish()

    async def configure(
        self,
        *,
        scenario_id: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> ScenarioCommandResult:
        return await self._command(
            lambda: self.scenario.configure(
                scenario_id=scenario_id, latitude=latitude, longitude=longitude
            )
        )

    async def start(self) -> ScenarioCommandResult:
        return await self._command(self.scenario.start)

    async def authorize(
        self, engagement_id: str, interceptors: int | None = None
    ) -> ScenarioCommandResult:
        return await self._command(lambda: self.scenario.authorize(engagement_id, interceptors))

    async def decline(self, engagement_id: str) -> ScenarioCommandResult:
        return await self._command(lambda: self.scenario.decline(engagement_id))

    async def reassign(self, engagement_id: str, node_id: str) -> ScenarioCommandResult:
        return await self._command(lambda: self.scenario.reassign(engagement_id, node_id))

    async def reset(self) -> ScenarioCommandResult:
        return await self._command(self.scenario.reset)

    async def wait_for_update(
        self, seen_version: int, timeout: float
    ) -> tuple[int, ScenarioSnapshot]:
        """Return the next snapshot after `seen_version`, or the current one on timeout."""
        async with self._changed:
            if self._version == seen_version:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._changed.wait(), timeout)
            return self._version, self._snapshot

    async def _command(self, action: Callable[[], CommandOutcome]) -> ScenarioCommandResult:
        outcome = action()
        await self._publish()
        return ScenarioCommandResult(
            ok=outcome.ok, detail=outcome.detail, snapshot=self._snapshot
        )

    async def _publish(self) -> None:
        async with self._changed:
            self._version += 1
            self._snapshot = self.scenario.snapshot().model_copy(
                update={"revision": self._version}
            )
            self._changed.notify_all()
