# `aki.api` API 文档

> REST API — FastAPI 服务器、会话管理、请求/响应模型

---

## `aki.api.models`

**文件路径：** `aki/api/models.py`

API request/response models for Aki HTTP server.
---

#### class `CreateSessionRequest(BaseModel)`

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `user_id` | `str` | `` |  |
| `role` | `str` | `'orchestrator'` |  |
| `default_llm` | `str` | `'openai:gpt-4o'` |  |
| `mcp_url` | `str | None` | `None` |  |
| `user_context` | `dict[str, Any] | None` | `None` |  |


---

#### class `CreateSessionResponse(BaseModel)`

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `session_id` | `str` | `` |  |
| `agent_id` | `str` | `` |  |
| `status` | `str` | `'connected'` |  |


---

#### class `SendMessageRequest(BaseModel)`

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `message` | `str` | `` |  |
| `history` | `list[dict[str, Any]]` | `` |  |
| `user_id` | `str | None` | `None` |  |


---

#### class `SendMessageResponse(BaseModel)`

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `reply` | `str` | `` |  |
| `system_events` | `list[str]` | `` |  |
| `profile_updates` | `dict[str, Any]` | `` |  |
| `preference_updates` | `dict[str, Any]` | `` |  |
| `next_status` | `str | None` | `None` |  |


---

#### class `SessionHistoryResponse(BaseModel)`

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `session_id` | `str` | `` |  |
| `messages` | `list[dict[str, Any]]` | `` |  |


---

#### class `HealthResponse(BaseModel)`

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `status` | `str` | `'ok'` |  |
| `service` | `str` | `'aki'` |  |
| `active_sessions` | `int` | `0` |  |



---

## `aki.api.routes`

**文件路径：** `aki/api/routes.py`

API route handlers for Aki HTTP server.
---

#### `async def create_session(req: CreateSessionRequest)` <small>(L21)</small>

Create a new persistent agent session.


---

#### `async def send_message(session_id: str, req: SendMessageRequest)` <small>(L45)</small>

Send a message to an agent session and get a response.


---

#### `async def get_session_history(session_id: str)` <small>(L61)</small>

Get conversation history for a session.


---

#### `async def delete_session(session_id: str)` <small>(L73)</small>

End and cleanup a session.


---

#### `async def health_check()` <small>(L81)</small>

Health check endpoint.



---

## `aki.api.server`

**文件路径：** `aki/api/server.py`

Aki HTTP API server for interactive agent sessions.
---

#### `async def lifespan(app: FastAPI)` <small>(L15)</small>

Startup/shutdown lifecycle for the API server.


---

#### `def run_server(host: str = '0.0.0.0', port: int = 8080) -> None` <small>(L41)</small>

Start the Aki HTTP API server.



---

## `aki.api.session_manager`

**文件路径：** `aki/api/session_manager.py`

Session manager for persistent multi-turn agent conversations.
---

#### class `SessionState`

```
Tracks a persistent agent session for a user.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `session_id` | `str` | `` |  |
| `user_id` | `str` | `` |  |
| `orchestrator` | `AgentOrchestrator` | `` |  |
| `agent` | `Optional[UniversalAgent]` | `None` |  |
| `agent_context` | `Optional[AgentContext]` | `None` |  |
| `conversation_history` | `list[dict[str, Any]]` | `field(default_factory=list)` |  |
| `created_at` | `datetime` | `field(default_factory=lambda: datetime.now(timezone.utc))` |  |
| `last_active` | `datetime` | `field(default_factory=lambda: datetime.now(timezone.utc))` |  |


---

#### class `SessionManager`

```
Manages persistent agent sessions for multi-turn conversations.

Each session keeps a single ``UniversalAgent`` alive across messages so
the agent can maintain context via conversation history and its memory
system.
```

**方法：**

##### `def __init__(self) -> None` <small>(L37)</small>

##### `async def create_session(self, user_id: str, role: str = 'orchestrator', llm_config: str = 'openai:gpt-4o', extra_tools: list[Any] | None = None, auto_load_mcp: bool = True, session_id: str | None = None, user_context: dict[str, Any] | None = None) -> SessionState` <small>(L40)</small>

Create a new persistent session with its own agent.

Args:
    extra_tools: Additional BaseTool instances (e.g. MCP tools) to
        make available alongside the auto-loaded registry tools.
    auto_load_mcp: If True, automatically discover tools from MCP
        servers configured in ``.aki/mcp.json``.
    session_id: Optional deterministic ID (used by Gateway to
        restore persisted sessions).  Generates a UUID if omitted.

##### `async def send_message(self, session_id: str, message: str, history: list[dict[str, Any]] | None = None) -> dict[str, Any]` <small>(L106)</small>

Send a message to an existing session and get a response.

The agent is reused across turns — conversation history is passed to
``agent.run_turn()`` so the LLM sees prior context.

##### `def get_history(self, session_id: str) -> list[dict[str, Any]]` <small>(L200)</small>

Return conversation history for a session.

##### `def get_session(self, session_id: str) -> SessionState` <small>(L207)</small>

Return session state (raises KeyError if not found).

##### `def cleanup_session(self, session_id: str) -> None` <small>(L214)</small>

Remove a session and free its resources.

##### `def cleanup_idle(self, max_idle_minutes: int = 30) -> int` <small>(L218)</small>

Remove sessions that have been idle for too long. Returns count removed.

##### `def active_count(self) -> int` <small>(L231)</small>


---

#### `def get_session_manager() -> SessionManager` <small>(L349)</small>



---

