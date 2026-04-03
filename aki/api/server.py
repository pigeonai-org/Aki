"""Aki HTTP API server for interactive agent sessions."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aki.api.routes import router
from aki.api.session_manager import get_session_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle for the API server."""
    yield
    # Cleanup all sessions on shutdown
    manager = get_session_manager()
    manager.cleanup_idle(max_idle_minutes=0)


app = FastAPI(
    title="Aki API",
    version="0.1.0",
    description="Aki agent HTTP API for interactive multi-turn conversations",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


def run_server(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Start the Aki HTTP API server."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)
