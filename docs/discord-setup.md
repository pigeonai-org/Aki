# Connecting Aki to Discord

This guide walks you through setting up Aki as a Discord bot. Takes about 5 minutes.

## 1. Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application**, name it whatever you want (e.g. "Aki")
3. Go to the **Bot** tab on the left
4. Click **Reset Token**, copy the token — you'll need it in step 3
5. Scroll down to **Privileged Gateway Intents** and enable:
   - **Message Content Intent** (required — Aki needs to read messages)

## 2. Invite the Bot to Your Server

1. Go to the **OAuth2 → URL Generator** tab
2. Under **Scopes**, check `bot`
3. Under **Bot Permissions**, check:
   - Send Messages
   - Read Message History
   - View Channels
4. Copy the generated URL and open it in your browser
5. Select the server you want to add Aki to, confirm

## 3. Configure Aki

Add the bot token to your `.env` file:

```bash
# Required
AKI_GATEWAY_DISCORD_TOKEN=your-bot-token-here

# Optional: restrict to specific channels (comma-separated channel IDs)
# If omitted, Aki responds in ALL channels it can see — usually what you want
# Only set this if you want to limit Aki to certain channels
# AKI_GATEWAY_DISCORD_CHANNEL_IDS=1234567890,0987654321

# LLM for the gateway (defaults to AKI_DEFAULT_LLM if not set)
AKI_GATEWAY_DEFAULT_LLM="anthropic:claude-sonnet-4-20250514"
```

To get a channel ID: enable Developer Mode in Discord settings (App Settings → Advanced → Developer Mode), then right-click any channel → Copy Channel ID.

## 4. Install Discord Dependency

```bash
uv sync --extra discord
```

## 5. Start

```bash
aki gateway
```

That's it. Aki will connect to Discord and start responding to messages in the allowed channels. The gateway also starts a REST API on port 8080 simultaneously.

You should see:

```
Discord adapter registered
Discord connected as Aki#1234
```

## How It Works

Each Discord channel gets its own persistent session:

- **Session ID**: `discord:{channel_id}` — one conversation thread per channel
- **Persistence**: Conversations are saved to `.aki/sessions/` as JSONL and survive restarts
- **Context Compaction**: When conversations get long, older messages are LLM-summarized to stay within token limits
- **Concurrency**: Each channel has its own lock — messages in one channel don't block another

Aki uses whatever persona is currently active (default: `aki`). To switch personas, update `.aki/personality/active.json` or use the `/persona` command in the CLI before starting the gateway.

## Options

```bash
# Custom host/port for the REST API
aki gateway --host 0.0.0.0 --port 3000

# Override token via CLI (instead of .env)
aki gateway --discord-token YOUR_TOKEN

# Restrict channels via CLI
aki gateway --discord-channels "123456,789012"
```

## Troubleshooting

**Bot connects but doesn't respond:**
- Check that Message Content Intent is enabled in the Developer Portal
- Check that the bot has permission to read/send in the target channel
- If using `AKI_GATEWAY_DISCORD_CHANNEL_IDS`, verify the channel IDs are correct

**"discord.py is required" error:**
- Run `uv sync --extra discord` to install the dependency

**Bot responds but output is generic (no personality):**
- Make sure the `aki/personality/aki/aki.md` file exists
- The gateway loads the default "aki" persona automatically

**Long messages get cut off:**
- Discord has a 2000-character limit per message. Aki automatically chunks long responses.
