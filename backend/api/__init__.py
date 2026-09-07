"""HTTP and WebSocket API layer.

deps.py     shared FastAPI dependencies
models.py   inbound request bodies
routers/    REST endpoints, one module per role
websocket.py  the live telemetry channel
"""

from backend.api.routers import api_router

__all__ = ["api_router"]
