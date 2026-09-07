"""SkunkLabs MVP V0 backend entry point.

Run with:  python -m backend.main

Application assembly only — no request handling, no mission logic. Routes
live in `backend.api.routers`, the frame loop in `backend.pipeline`.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import websocket
from backend.api.routers import api_router
from backend.config.settings import Settings, get_settings
from backend.pipeline import MissionPipeline

log = logging.getLogger("skunklabs")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-7s %(name)-28s %(message)s",
        datefmt="%H:%M:%S",
    )


def _lifespan(settings: Settings):
    """Own the pipeline for the life of the app.

    The pipeline holds a worker thread and an open video device, so it is
    started and stopped with the application rather than lazily on first
    request — a half-initialised pipeline behind a live port is exactly the
    failure that is hardest to diagnose during a demo.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        pipeline = MissionPipeline(settings)
        app.state.pipeline = pipeline
        pipeline.start()
        log.info("SkunkLabs V0 backend ready on http://%s:%d", settings.host, settings.port)
        try:
            yield
        finally:
            pipeline.stop()

    return lifespan


def _mount_frontend(app: FastAPI, settings: Settings) -> None:
    """Serve the built frontend, when there is one.

    In development the Vite dev server proxies to this backend and this does
    nothing. In production `npm run build` produces `frontend/dist` and the
    whole console is served from a single origin — no CORS, no second port,
    one process to deploy.
    """
    dist = settings.frontend_dist
    if not dist.is_dir() or not (dist / "index.html").exists():
        log.info("No frontend build at %s — API only (run `npm run build`).", dist)
        return

    # Imported here so a deployment without a build never pays for it.
    from fastapi.staticfiles import StaticFiles

    # Mounted last, at the root, so every /api and /ws route already
    # registered wins over the catch-all. `html=True` serves index.html for
    # unknown paths, which is what a client-side-routed SPA needs.
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
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
            "Local detection, tracking and operator engagement demo. "
            "Actuation is simulated and benign."
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
