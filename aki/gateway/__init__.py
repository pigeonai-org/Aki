"""Aki Gateway — multi-platform messaging layer.

Start the gateway with::

    aki gateway --discord-token YOUR_TOKEN

Or programmatically::

    from aki.gateway import launch_gateway
    await launch_gateway(discord_token="...")
"""

from __future__ import annotations

import logging
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def launch_gateway(
    host: str = "0.0.0.0",
    port: int = 8080,
    discord_token: Optional[str] = None,
    discord_channels: Optional[list[str]] = None,
) -> None:
    """Start the unified gateway process: FastAPI + platform adapters.

    This runs the REST API server and any configured platform adapters
    (e.g. Discord bot) in a single asyncio event loop.
    """
    from aki.api.session_manager import get_session_manager
    from aki.config.settings import get_settings
    from aki.gateway.compaction import ContextCompactor
    from aki.gateway.gateway import Gateway
    from aki.gateway.persistence import SessionPersistence

    # Enable agent verbose logging so thoughts/actions print to console
    from aki.agent.logger import set_verbose
    set_verbose(True)

    settings = get_settings()
    gw_settings = settings.gateway

    # Resolve config fallbacks
    token = discord_token or gw_settings.discord_token
    channels = discord_channels
    if channels is None and gw_settings.discord_channel_ids:
        channels = [c.strip() for c in gw_settings.discord_channel_ids.split(",") if c.strip()]

    # Build components
    sm = get_session_manager()
    persistence = SessionPersistence(base_dir=gw_settings.session_dir)

    # Build compactor (needs an LLM instance)
    compactor: ContextCompactor | None = None
    try:
        from aki.api.session_manager import _build_llm

        llm = _build_llm(gw_settings.default_llm)
        if llm is not None:
            compactor = ContextCompactor(
                llm=llm,
                max_context_tokens=gw_settings.compaction_max_tokens,
                soft_threshold_ratio=gw_settings.compaction_threshold,
            )
    except Exception as exc:
        logger.warning("Could not build compactor LLM: %s — compaction disabled", exc)

    gateway = Gateway(
        session_manager=sm,
        persistence=persistence,
        compactor=compactor,
        default_llm=gw_settings.default_llm,
    )

    # Register platform adapters
    if token:
        from aki.gateway.adapters.discord_adapter import DiscordAdapter

        gateway.register_adapter(DiscordAdapter(token=token, allowed_channel_ids=channels))
        logger.info("Discord adapter registered")
    else:
        logger.info("No Discord token — running REST API only")

    # Start gateway (loads index, starts adapters)
    await gateway.start()

    # Run FastAPI in the same event loop
    import uvicorn

    from aki.api.server import app

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    try:
        await server.serve()
    finally:
        await gateway.stop()
