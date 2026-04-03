# `aki.hooks` API 文档

> Hook + 权限系统 — 生命周期事件分发、工具权限规则求值

---

## `aki.hooks.engine`

**文件路径：** `aki/hooks/engine.py`

Hook Engine

Central event dispatch system for lifecycle hooks.
Handlers are registered per EventType and fire in priority order.
---

#### class `_RegisteredHandler`

```
Internal wrapper tracking handler priority.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|

**方法：**

##### `def __init__(self, handler: HookHandler, priority: int) -> None` <small>(L24)</small>


---

#### class `HookEngine`

```
Central event dispatch for lifecycle hooks.

Handlers are registered per EventType and fire in ascending priority order.
Lower priority numbers execute first.

Usage::

    engine = HookEngine()

    async def my_hook(event: HookEvent) -> HookResult:
        print(f"Tool {event.data['tool_name']} was called")
        return HookResult()

    engine.register(EventType.PRE_TOOL_USE, my_hook, priority=10)
    result = await engine.fire(HookEvent(event_type=EventType.PRE_TOOL_USE, data={...}))
```

**方法：**

##### `def __init__(self) -> None` <small>(L48)</small>

##### `def register(self, event_type: EventType, handler: HookHandler, priority: int = 0) -> None` <small>(L51)</small>

Register a hook handler for an event type.

Args:
    event_type: The event to listen for.
    handler: Async callable receiving HookEvent, returning HookResult.
    priority: Execution order (lower runs first). Default 0.

##### `def unregister(self, event_type: EventType, handler: HookHandler) -> None` <small>(L70)</small>

Remove a previously registered handler.

##### `async def fire(self, event: HookEvent) -> HookResult` <small>(L75)</small>

Fire an event and return the merged result.

Handlers execute in priority order. If any handler sets ``allow=False``,
the merged result will have ``allow=False`` and execution stops early.
The last non-None ``modified_data`` wins.

Returns HookResult(allow=True) immediately when no handlers are registered
(zero overhead in the common case).

##### `async def fire_all(self, event: HookEvent) -> list[HookResult]` <small>(L108)</small>

Fire an event and collect results from all handlers (no early stopping).

Useful for notification-style events where every handler should run.

##### `def has_handlers(self, event_type: EventType) -> bool` <small>(L127)</small>

Check if any handlers are registered for an event type.

##### `def clear(self, event_type: EventType | None = None) -> None` <small>(L131)</small>

Remove all handlers.

Args:
    event_type: If provided, only clear handlers for this event type.
                If None, clear all handlers.



---

## `aki.hooks.permission`

**文件路径：** `aki/hooks/permission.py`

Permission Engine

Evaluates tool permission against an agent's permission mode and rules.
Integrates with HookEngine for PERMISSION_REQUEST events.
---

#### class `PermissionEngine`

```
Evaluates whether a tool call is permitted given a mode and a rule set.

Decision flow:
1. BYPASS mode -> always allow
2. STRICT mode -> always fire PERMISSION_REQUEST hook
3. Check deny rules -> if matched, deny
4. Check allow rules -> if matched, allow
5. Check ask rules -> if matched, fire PERMISSION_REQUEST hook
6. DEFAULT mode -> allow (no matching rule = safe)
7. AUTO mode -> allow (rely on external classifier hook if registered)
```

**方法：**

##### `def __init__(self, hook_engine: HookEngine) -> None` <small>(L33)</small>

##### `async def check_permission(self, agent_id: str, tool_name: str, tool_params: dict[str, Any], mode: PermissionMode, rules: list[PermissionRule]) -> bool` <small>(L36)</small>

Evaluate whether a tool call is permitted.

Args:
    agent_id: The calling agent's ID.
    tool_name: Name of the tool being invoked.
    tool_params: Parameters passed to the tool.
    mode: The agent's current permission mode.
    rules: Ordered list of permission rules.

Returns:
    True if the call is permitted, False otherwise.



---

## `aki.hooks.rules`

**文件路径：** `aki/hooks/rules.py`

Permission Rules and Modes

Defines permission modes for agents and glob-based permission rules for tools.
---

#### class `PermissionMode(str, Enum)`

```
Agent permission mode controlling tool access behavior.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `DEFAULT` | `` | `'default'` |  |
| `BYPASS` | `` | `'bypass'` |  |
| `AUTO` | `` | `'auto'` |  |
| `PLAN` | `` | `'plan'` |  |
| `STRICT` | `` | `'strict'` |  |


---

#### class `PermissionRule(BaseModel)`

```
A single permission rule matching tools by glob pattern.

Examples:
    PermissionRule(tool_pattern="file_write", action="ask")
    PermissionRule(tool_pattern="web_*", action="allow")
    PermissionRule(tool_pattern="*", action="deny")
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `tool_pattern` | `str` | `` | Glob pattern matching tool names |
| `action` | `str` | `` | Action:  |
| `reason` | `str` | `''` | Human-readable reason for this rule |

**方法：**

##### `def model_post_init(self, __context: Any) -> None` <small>(L37)</small>



---

## `aki.hooks.types`

**文件路径：** `aki/hooks/types.py`

Hook Event Types

Defines the event types, event payloads, and hook results for the lifecycle hook system.
---

#### class `EventType(str, Enum)`

```
All supported hook event types.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `SESSION_START` | `` | `'session_start'` |  |
| `SESSION_END` | `` | `'session_end'` |  |
| `PRE_TOOL_USE` | `` | `'pre_tool_use'` |  |
| `POST_TOOL_USE` | `` | `'post_tool_use'` |  |
| `PERMISSION_REQUEST` | `` | `'permission_request'` |  |
| `AGENT_SPAWN` | `` | `'agent_spawn'` |  |
| `AGENT_COMPLETE` | `` | `'agent_complete'` |  |
| `CONTEXT_COMPACTION` | `` | `'context_compaction'` |  |
| `MODEL_FAILOVER` | `` | `'model_failover'` |  |
| `ERROR_RECOVERY` | `` | `'error_recovery'` |  |
| `MESSAGE_SEND` | `` | `'message_send'` |  |
| `MESSAGE_RECEIVE` | `` | `'message_receive'` |  |


---

#### class `HookEvent(BaseModel)`

```
Payload delivered to hook handlers when an event fires.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `event_type` | `EventType` | `` |  |
| `agent_id` | `str` | `''` |  |
| `timestamp` | `datetime` | `` |  |
| `data` | `dict[str, Any]` | `` |  |


---

#### class `HookResult(BaseModel)`

```
Result returned by a hook handler.

Handlers can:
- Block the operation by setting allow=False
- Modify the operation data via modified_data
- Attach a human-readable message
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `allow` | `bool` | `True` |  |
| `modified_data` | `Optional[dict[str, Any]]` | `None` |  |
| `message` | `str` | `''` |  |



---

