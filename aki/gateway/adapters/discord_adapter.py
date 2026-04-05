"""Discord platform adapter using discord.py.

Session mapping: ``"discord:{channel_id}"`` — one conversation per
channel or DM.  Different channels get separate sessions.

Install the optional dependency::

    pip install "aki[discord]"
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from aki.gateway.adapters.base import PlatformAdapter
from aki.gateway.types import InboundMessage, OutboundMessage, PlatformContext

logger = logging.getLogger(__name__)

# Discord has a 2 000 character limit per message.
_DISCORD_MAX_LEN = 2000


class DiscordAdapter(PlatformAdapter):
    """Adapter that connects a Discord bot to the Aki Gateway."""

    platform_name = "discord"  # type: ignore[assignment]

    def __init__(
        self,
        token: str,
        allowed_channel_ids: list[str] | None = None,
    ) -> None:
        self._token = token
        self._allowed_channels = set(allowed_channel_ids) if allowed_channel_ids else None
        self._client: object | None = None  # discord.Client (typed loosely to allow lazy import)
        self._on_message: Callable[[InboundMessage], Awaitable[OutboundMessage]] | None = None

    async def start(
        self,
        on_message: Callable[[InboundMessage], Awaitable[OutboundMessage]],
    ) -> None:
        try:
            import discord
        except ImportError as exc:
            raise ImportError(
                "discord.py is required for the Discord adapter. "
                "Install with: pip install 'aki[discord]'"
            ) from exc

        self._on_message = on_message

        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        self._client = client

        @client.event
        async def on_ready() -> None:
            logger.info("Discord connected as %s", client.user)

            # If this is a restart, notify active channels
            import os
            if os.environ.pop("AKI_RESTARTED", None):
                await self._notify_restart(client)

        @client.event
        async def on_message(message: discord.Message) -> None:
            # Ignore own messages and bots
            if message.author == client.user:
                return
            if message.author.bot:
                return

            # Channel filter (if configured)
            if self._allowed_channels and str(message.channel.id) not in self._allowed_channels:
                return

            # Skip empty messages (e.g. image-only)
            if not message.content.strip():
                return

            ctx = PlatformContext(
                platform="discord",
                channel_id=str(message.channel.id),
                user_id=str(message.author.id),
                user_display_name=message.author.display_name,
                raw_event=message,
            )
            inbound = InboundMessage(
                text=message.content,
                platform_ctx=ctx,
                timestamp=message.created_at,
            )

            try:
                outbound = await self._on_message(inbound)
                await self.send_reply(outbound)
            except Exception as exc:
                logger.exception("Error handling Discord message: %s", exc)
                try:
                    await message.channel.send(
                        f"Sorry, I encountered an error: {exc!s:.200}"
                    )
                except Exception:
                    pass

        await client.start(self._token)

    async def stop(self) -> None:
        if self._client is not None:
            import discord

            if isinstance(self._client, discord.Client):
                await self._client.close()

    async def send_typing(self, ctx: PlatformContext) -> None:
        if ctx.raw_event is not None and hasattr(ctx.raw_event, "channel"):
            try:
                await ctx.raw_event.channel.typing()
            except Exception:
                pass

    async def send_reply(self, msg: OutboundMessage) -> None:
        if msg.platform_ctx.raw_event is None:
            return
        channel = msg.platform_ctx.raw_event.channel
        text = msg.text
        # Discord 2000 char limit — chunk if needed
        while text:
            chunk, text = text[:_DISCORD_MAX_LEN], text[_DISCORD_MAX_LEN:]
            await channel.send(chunk)

    async def _notify_restart(self, client: Any) -> None:
        """Send a restart notification to all known channels."""
        # Collect channel IDs from allowed list or all guilds
        channel_ids: set[str] = set()
        if self._allowed_channels:
            channel_ids = set(self._allowed_channels)
        else:
            # Notify all text channels in all guilds (risky in big servers, so limit to allowed)
            # If no allowlist, skip — we don't want to spam every channel
            logger.info("No channel allowlist — skipping restart notification")
            return

        for cid in channel_ids:
            try:
                channel = client.get_channel(int(cid))
                if channel is None:
                    channel = await client.fetch_channel(int(cid))
                if channel is not None:
                    await channel.send("Restarted successfully.")
            except Exception as e:
                logger.warning("Failed to notify channel %s: %s", cid, e)
