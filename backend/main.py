"""SkunkLabs MVP V0 backend entry point.

Run with:  python -m backend.main

Application assembly only - no request handling, no mission logic. Routes
live in `backend.api.routers`, the launcher scenario in `backend.scenario`,
and the optional video frame loop in `backend.pipeline`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from dataclasses import replace

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import websocket
from backend.api.routers import api_router
from backend.config.settings import Settings, get_settings
from backend.pipeline import MissionPipeline
from backend.scenario import DefenseScenario, ScenarioService
from backend.scenario.config import ScenarioConfig, SiteSetup

log = logging.getLogger("skunklabs")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-7s %(name)-28s %(message)s",
        datefmt="%H:%M:%S",
    )


def _scenario_config(settings: Settings) -> ScenarioConfig:
    """The scenario layout, with the site pinned by settings when they say so.

    A browser that reports its position still wins; this only moves the
    fallback, so a demo can be centred on a chosen place without touching code.
    """
    site = SiteSetup()
    if settings.site_latitude is not None and settings.site_longitude is not None:
        site = replace(site, latitude=settings.site_latitude, longitude=settings.site_longitude)
    if settings.site_name:
        site = replace(site, name=settings.site_name)
    return ScenarioConfig(site=site)


def _lifespan(settings: Settings):
    """Own the launcher scenario - and, when enabled, the video pipeline.

    The scenario ticks on this event loop for the life of the app. The video
    pipeline holds a worker thread and an open video device, so when enabled
    it is started and stopped with the application rather than lazily on first
    request - a half-initialised pipeline behind a live port is exactly the
    failure that is hardest to diagnose during a demo.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scenario = ScenarioService(DefenseScenario(_scenario_config(settings)))
        app.state.scenario = scenario
        ticker = asyncio.create_task(scenario.run(), name="defense-scenario")

        pipeline: MissionPipeline | None = None
        if settings.video_pipeline_enabled:
            pipeline = MissionPipeline(settings)
            pipeline.start()
        app.state.pipeline = pipeline

        log.info(
            "SkunkLabs V0 backend ready on http://%s:%d (video pipeline %s)",
            settings.host,
            settings.port,
            "enabled" if pipeline else "disabled",
        )
        try:
            yield
        finally:
            ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ticker
            if pipeline is not None:
                pipeline.stop()

    return lifespan


def _mount_frontend(app: FastAPI, settings: Settings) -> None:
    """Serve the built frontend, when there is one.

    In development the Vite dev server proxies to this backend and this does
    nothing. In production `npm run build` produces `frontend/dist` and the
    whole console is served from a single origin - no CORS, no second port,
    one process to deploy.
    """
    dist = settings.frontend_dist
    if not dist.is_dir() or not (dist / "index.html").exists():
        log.info("No frontend build at %s - API only (run `npm run build`).", dist)
        return

    # Imported here so a deployment without a build never pays for it.
    from fastapi.staticfiles import StaticFiles
    from starlette.exceptions import HTTPException

    class SpaStaticFiles(StaticFiles):
        """Static files, with the client-side routes (/map, /launcher) answered
        by index.html. Unknown API paths and missing files (anything with an
        extension) still 404 - a missing CAD model must not come back as HTML."""

        async def get_response(self, path: str, scope):
            try:
                return await super().get_response(path, scope)
            except HTTPException as exc:
                last_segment = path.rsplit("/", 1)[-1]
                if exc.status_code != 404 or path.startswith("api") or "." in last_segment:
                    raise
                return await super().get_response("index.html", scope)

    # Mounted last, at the root, so every /api and /ws route already
    # registered wins over the catch-all.
    app.mount("/", SpaStaticFiles(directory=dist, html=True), name="frontend")
    log.info("Serving frontend from %s", dist)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Takes settings so a test can construct an app with an overridden
    configuration instead of mutating the cached global.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="SkunkLabs MVP V0",
        description=(
            "Launcher orientation and operator authorization demonstrator. "
            "Every launch, trajectory and intercept is a simulation; nothing is actuated."
        ),
        version="0.1.0",
        lifespan=_lifespan(settings),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    app.include_router(websocket.router)
    _mount_frontend(app, settings)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
