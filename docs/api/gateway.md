# `aki.gateway` API 文档

> 多平台网关 — 消息队列、会话持久化、平台适配器（Discord 等）

---

## `aki.gateway.compaction`

**文件路径：** `aki/gateway/compaction.py`

Context compaction for long-running conversations.

When conversation_history grows too large for the model's context window,
older messages are summarized into a single ``[Conversation summary]``
system message.  Recent messages are kept intact.

The memory flush step is handled by ``SessionManager._memory_review()``
which already runs after every turn — no additional action needed here.
---

#### class `ContextCompactor`

```
Summarises old conversation history to stay within context limits.
```

**方法：**

##### `def __init__(self, llm: LLMInterface, max_context_tokens: int = 8000, soft_threshold_ratio: float = 0.8, keep_recent: int = 10) -> None` <small>(L29)</small>

##### `def estimate_tokens(history: list[dict[str, Any]]) -> int` <small>(L46)</small>

Cheap token count approximation (characters / 4).

##### `def needs_compaction(self, history: list[dict[str, Any]]) -> bool` <small>(L51)</small>

Return ``True`` if history exceeds the soft threshold.

##### `async def compact(self, history: list[dict[str, Any]], persistence: Any | None = None, session_id: str | None = None) -> list[dict[str, Any]]` <small>(L59)</small>

Compact *history* by summarising older messages.

Returns a new (shorter) history list.  If *persistence* and
*session_id* are provided, a ``compaction`` entry is appended to
the JSONL transcript.



---

## `aki.gateway.gateway`

**文件路径：** `aki/gateway/gateway.py`

Gateway hub — connects SessionManager, LaneQueue, Persistence, and Platform Adapters.

The Gateway is the central routing layer.  For every inbound message it:

1. Resolves (or creates) a session for the platform + channel.
2. Fires a typing indicator immediately.
3. Acquires the per-session lane lock (serialises concurrent messages).
4. Persists the inbound message to JSONL.
5. Runs context compaction if history is too long.
6. Delegates to ``SessionManager.send_message()``.
7. Persists the assistant reply to JSONL.
8. Returns an ``OutboundMessage`` for the adapter to deliver.
---

#### class `Gateway`

```
Central message routing hub for multi-platform agent access.
```

**方法：**

##### `def __init__(self, session_manager: SessionManager, persistence: SessionPersistence, compactor: ContextCompactor | None = None, default_role: str = 'orchestrator', default_llm: str = 'openai:gpt-4o') -> None` <small>(L36)</small>

##### `def register_adapter(self, adapter: PlatformAdapter) -> None` <small>(L57)</small>

Register a platform adapter to be started with the Gateway.

##### `async def start(self) -> None` <small>(L65)</small>

Load persisted state and start all registered adapters.

##### `async def stop(self) -> None` <small>(L77)</small>

Gracefully shut down all adapters.

##### `async def handle_message(self, msg: InboundMessage) -> OutboundMessage` <small>(L93)</small>

Process one inbound message end-to-end.

This method is passed as the ``on_message`` callback to adapters.



---

## `aki.gateway.lane_queue`

**文件路径：** `aki/gateway/lane_queue.py`

Per-session serialization queue using asyncio.Lock.

Guarantees that at most one agent turn runs per session at a time,
preventing concurrent state corruption in UniversalAgent.
---

#### class `LaneQueue`

```
Ensures at most one agent turn runs per session at a time.

Each session gets its own ``asyncio.Lock``.  When a second message
arrives while the first is still processing, it ``await`` s on the
lock and executes sequentially — no interleaving of ``run_turn()``
calls on the same ``UniversalAgent`` instance.
```

**方法：**

##### `def __init__(self) -> None` <small>(L23)</small>

##### `async def acquire(self, session_id: str) -> AsyncIterator[None]` <small>(L33)</small>

Acquire exclusive access to a session lane.

Usage::

    async with lane_queue.acquire(session_id):
        await session_manager.send_message(session_id, text)

##### `def pending_count(self, session_id: str) -> int` <small>(L51)</small>

Return the number of messages waiting (including the active one).

##### `def cleanup(self, session_id: str) -> None` <small>(L55)</small>

Remove lock state for a session that has been destroyed.



---

## `aki.gateway.persistence`

**文件路径：** `aki/gateway/persistence.py`

JSONL session persistence and sessions index.

Storage layout::

    .aki/sessions/
    ├── sessions.json            # platform:channel → session metadata
    └── {session_id}.jsonl       # append-only transcript per session

``sessions.json`` is a small mutable index.  Each ``.jsonl`` file is
append-only — messages, tool calls, and compaction entries are appended
as one JSON object per line.
---

#### class `SessionPersistence`

```
Manages JSONL transcripts and the sessions index file.
```

**方法：**

##### `def __init__(self, base_dir: str | Path | None = None) -> None` <small>(L25)</small>

##### `def load_index(self) -> dict[str, dict[str, Any]]` <small>(L33)</small>

Load ``sessions.json`` from disk.  Returns the loaded dict.

##### `def save_index(self) -> None` <small>(L45)</small>

Persist the in-memory index to ``sessions.json``.

##### `def lookup_session(self, platform: str, channel_id: str) -> str | None` <small>(L54)</small>

Return ``session_id`` for a *platform:channel_id* key, or ``None``.

##### `def register_session(self, session_id: str, platform: str, channel_id: str, user_id: str, role: str = 'orchestrator', llm_config: str = 'openai:gpt-4o') -> None` <small>(L60)</small>

Create an index entry for a new session and flush to disk.

##### `def touch_session(self, platform: str, channel_id: str) -> None` <small>(L84)</small>

Update the ``updated_at`` timestamp for an existing entry.

##### `def remove_session(self, platform: str, channel_id: str) -> None` <small>(L91)</small>

Remove a session from the index (transcript file is kept).

##### `def append_entry(self, session_id: str, entry: dict[str, Any]) -> None` <small>(L104)</small>

Append one JSON line to the session transcript.

##### `def load_transcript(self, session_id: str) -> list[dict[str, Any]]` <small>(L112)</small>

Read all entries from a session transcript.

##### `def rebuild_history(self, session_id: str) -> list[dict[str, Any]]` <small>(L128)</small>

Rebuild ``conversation_history`` from the JSONL transcript.

Applies compaction entries: when a ``compaction`` entry is found,
all prior ``user``/``assistant`` messages are replaced by the
summary.  Returns a list of ``{role, content}`` dicts suitable
for ``SessionManager``.

##### `def list_sessions(self) -> dict[str, dict[str, Any]]` <small>(L160)</small>

Return the full index (defensive copy).



---

## `aki.gateway.types`

**文件路径：** `aki/gateway/types.py`

Unified message types for the Gateway layer.
---

#### class `PlatformContext`

```
Opaque platform metadata carried alongside a message.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `platform` | `str` | `` |  |
| `channel_id` | `str` | `` |  |
| `user_id` | `str` | `` |  |
| `user_display_name` | `str` | `''` |  |
| `raw_event` | `Any` | `None` |  |


---

#### class `InboundMessage`

```
Platform-agnostic normalized message entering the system.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `text` | `str` | `` |  |
| `platform_ctx` | `PlatformContext` | `` |  |
| `timestamp` | `datetime` | `field(default_factory=lambda: datetime.now(timezone.utc))` |  |
| `message_id` | `str` | `field(default_factory=lambda: str(uuid4()))` |  |


---

#### class `OutboundMessage`

```
Reply produced by the Gateway, ready for platform delivery.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `text` | `str` | `` |  |
| `session_id` | `str` | `` |  |
| `platform_ctx` | `PlatformContext` | `` |  |
| `in_reply_to` | `str` | `` |  |



---

## `aki.gateway.adapters.base`

**文件路径：** `aki/gateway/adapters/base.py`

Abstract base class for platform adapters.

Each messaging platform (Discord, Telegram, Slack, …) gets its own
adapter that normalises platform-specific events into
:class:`InboundMessage` and delivers :class:`OutboundMessage` back.

The adapter does **not** need to know about the Gateway internals — it
receives a callback (``on_message``) and uses it to process each
inbound message.
---

#### class `PlatformAdapter(ABC)`

```
Abstract base for messaging platform integrations.
```

**方法：**

##### `def platform_name(self) -> str` <small>(L25)</small>

Unique platform identifier, e.g. ``'discord'``, ``'telegram'``.

##### `async def start(self, on_message: Callable[[InboundMessage], Awaitable[OutboundMessage]]) -> None` <small>(L29)</small>

Start listening for messages.

The adapter must call *on_message* for each inbound message it
receives and deliver the returned ``OutboundMessage`` back to the
platform (typically via :meth:`send_reply`).

##### `async def stop(self) -> None` <small>(L41)</small>

Gracefully disconnect from the platform.

##### `async def send_typing(self, ctx: PlatformContext) -> None` <small>(L45)</small>

Send a typing / "agent is thinking" indicator.

##### `async def send_reply(self, msg: OutboundMessage) -> None` <small>(L49)</small>

Deliver a reply message to the platform.



---

## `aki.gateway.adapters.discord_adapter`

**文件路径：** `aki/gateway/adapters/discord_adapter.py`

Discord platform adapter using discord.py.

Session mapping: ``"discord:{channel_id}"`` — one conversation per
channel or DM.  Different channels get separate sessions.

Install the optional dependency::

    pip install "aki[discord]"
---

#### class `DiscordAdapter(PlatformAdapter)`

```
Adapter that connects a Discord bot to the Aki Gateway.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `platform_name` | `` | `'discord'` |  |

**方法：**

##### `def __init__(self, token: str, allowed_channel_ids: list[str] | None = None) -> None` <small>(L30)</small>

##### `async def start(self, on_message: Callable[[InboundMessage], Awaitable[OutboundMessage]]) -> None` <small>(L40)</small>

##### `async def stop(self) -> None` <small>(L106)</small>

##### `async def send_typing(self, ctx: PlatformContext) -> None` <small>(L113)</small>

##### `async def send_reply(self, msg: OutboundMessage) -> None` <small>(L120)</small>



---

