# `aki.agent` API 文档

> Agent 核心系统 — 包括 Agent 执行循环、编排器、持久化身份、Agent 间通信

---

## `aki.agent.agent_registry`

**文件路径：** `aki/agent/agent_registry.py`

Agent Registry

Discovers and manages persistent agent definitions from disk and programmatic registration.
---

#### class `AgentRegistry`

```
Discovers and manages agent definitions.

Sources (in priority order):
1. Programmatically registered definitions (via register())
2. Discovered from .aki/agents/<name>/agent.md files

Usage::

    registry = AgentRegistry(agents_dir=".aki/agents")
    registry.discover()

    defn = registry.get_definition("MediaExtractor")
    identity = registry.get_or_create_identity("MediaExtractor")
```

**方法：**

##### `def __init__(self, agents_dir: str = '.aki/agents') -> None` <small>(L40)</small>

##### `def discover(self) -> dict[str, AgentDefinition]` <small>(L45)</small>

Scan agents_dir for agent.md definitions.

Returns:
    Dict of discovered definitions (also stored internally).

##### `def register(self, definition: AgentDefinition) -> None` <small>(L60)</small>

Programmatically register an agent definition.

Takes priority over disk-discovered definitions with the same name.

##### `def get_definition(self, name: str) -> Optional[AgentDefinition]` <small>(L68)</small>

Get an agent definition by name.

Args:
    name: The agent name.

Returns:
    AgentDefinition if found, None otherwise.

##### `def get_or_create_identity(self, name: str) -> Optional[AgentIdentity]` <small>(L80)</small>

Get or create a persistent identity for an agent.

If the agent has been seen before, returns the existing identity
(with incremented session count). Otherwise creates a new one.

Args:
    name: The agent name.

Returns:
    AgentIdentity if definition exists, None otherwise.

##### `def list_agents(self) -> list[str]` <small>(L114)</small>

List all registered agent names.

##### `def has_agent(self, name: str) -> bool` <small>(L118)</small>

Check if an agent definition exists.

##### `def remove(self, name: str) -> None` <small>(L122)</small>

Remove an agent definition and its identity.



---

## `aki.agent.base`

**文件路径：** `aki/agent/base.py`

Universal Agent Core

Driven by personality configuration. Uses native tool calling — no manual ReACT loop.
The model decides when to call tools and when it's done.
---

#### class `AgentError(Exception)`

```
Base exception for agent errors.
```


---

#### class `DepthLimitExceeded(AgentError)`

```
Raised when agent depth limit is exceeded.
```


---

#### class `AgentLimitExceeded(AgentError)`

```
Raised when agent count limit is exceeded.
```


---

#### class `UniversalAgent`

```
A unified agent class driven by personality configuration.

Uses native tool calling: the LLM decides which tools to call and when to stop.
No manual observe/think/act/reflect loop needed — modern models handle this natively.
```

**方法：**

##### `def __init__(self, agent_name: Optional[str] = None, context: Optional[AgentContext] = None, llm: Optional[LLMInterface] = None, memory: Optional[Any] = None, tools: Optional[list[BaseTool]] = None, user_context: Optional[dict[str, Any]] = None, context_manager: Optional[ContextManager] = None, error_handler: Optional[ErrorRecoveryHandler] = None, identity: Optional[AgentIdentity] = None, hook_engine: Optional[HookEngine] = None, permission_engine: Optional[PermissionEngine] = None)` <small>(L51)</small>

##### `async def run_turn(self, user_message: str, conversation_history: list[dict[str, Any]]) -> str` <small>(L100)</small>

Process one user turn within an ongoing conversation.

##### `async def run(self, task: str) -> Any` <small>(L117)</small>

Native tool calling loop with context management and error recovery.

When a ContextManager is provided, the loop runs until the token budget
is exhausted (instead of a hard 20-iteration cap). When an
ErrorRecoveryHandler is provided, LLM errors are classified and
recovered automatically (compact, backoff, failover, or abort).
Both subsystems are optional — without them the agent degrades
gracefully to a safety cap of 200 iterations.



---

## `aki.agent.identity`

**文件路径：** `aki/agent/identity.py`

Agent Identity and Definition

Persistent agent identities loaded from markdown frontmatter files.
AgentDefinition is a superset of Role, enabling per-agent model, maxTurns,
permission mode, and workspace configuration.
---

#### class `AgentDefinition(BaseModel)`

```
Complete agent definition, loadable from .aki/agents/<name>/agent.md frontmatter.

Superset of the existing Role class:
- name, persona, system_prompt, allowed_tools (same as Role)
- model, max_turns, temperature, permission_mode, permission_rules (new)
- soul (extended personality document)
- tags (categorization)
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `str` | `` | Unique agent identifier |
| `agent_type` | `str` | `'worker'` |  |
| `persona` | `str` | `''` | High-level character description |
| `system_prompt` | `str` | `''` | Core instructions |
| `allowed_tools` | `list[str]` | `` | Tool whitelist |
| `model` | `Optional[str]` | `None` | Model override (e.g.  |
| `max_turns` | `int` | `20` | Maximum LLM turns per task |
| `temperature` | `float` | `0.7` | Sampling temperature |
| `permission_mode` | `PermissionMode` | `PermissionMode.DEFAULT` |  |
| `permission_rules` | `list[PermissionRule]` | `` |  |
| `workspace_dir` | `Optional[str]` | `None` | Per-agent state directory |
| `soul` | `Optional[str]` | `None` | Extended personality markdown |
| `tags` | `list[str]` | `` | Categorization tags |

**方法：**

##### `def from_markdown(cls, filepath: str) -> 'AgentDefinition'` <small>(L49)</small>

Load an agent definition from a markdown file with YAML frontmatter.

File format::

    ---
    name: MediaExtractor
    agent_type: specialist
    persona: "You are a Media Extractor..."
    allowed_tools: [audio_extract, audio_vad, transcribe]
    model: "qwen:qwen3-asr-flash"
    max_turns: 10
    ---
    (Optional markdown body used as extended system prompt / soul)

Args:
    filepath: Path to the agent.md file.

Returns:
    AgentDefinition parsed from the file.


---

#### class `AgentIdentity(BaseModel)`

```
Runtime identity of an active agent instance.

Tracks session count and state directory for persistent agents.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `agent_id` | `str` | `` | Unique runtime instance ID |
| `definition` | `AgentDefinition` | `` |  |
| `state_dir` | `str` | `''` | Path to agent |
| `created_at` | `str` | `` |  |
| `session_count` | `int` | `0` |  |

**方法：**

##### `def increment_session(self) -> None` <small>(L107)</small>

Record a new session for this agent.


---

#### `def discover_agent_definitions(agents_dir: str) -> dict[str, AgentDefinition]` <small>(L133)</small>

Discover agent definitions from a directory.

Scans ``agents_dir`` for subdirectories containing ``agent.md`` files.

Args:
    agents_dir: Path to the agents directory (e.g. ".aki/agents").

Returns:
    Dict mapping agent name to AgentDefinition.



---

## `aki.agent.logger`

**文件路径：** `aki/agent/logger.py`

Agent Logger

Provides formatted logging for agent tool calls and lifecycle events.
---

#### class `AgentLogger`

```
Logger for agent activities.
```

**方法：**

##### `def __init__(self, verbose: bool = True, console: Optional[Console] = None)` <small>(L16)</small>

##### `def set_verbose(self, verbose: bool) -> None` <small>(L21)</small>

##### `def indent(self) -> None` <small>(L24)</small>

##### `def dedent(self) -> None` <small>(L27)</small>

##### `def agent_start(self, agent_name: str, task: str, depth: int) -> None` <small>(L33)</small>

##### `def agent_end(self, agent_name: str, result: Any) -> None` <small>(L46)</small>

##### `def tool_calls(self, _agent_name: str, calls: list[Any]) -> None` <small>(L55)</small>

##### `def error(self, agent_name: str, error: str) -> None` <small>(L67)</small>

##### `def separator(self) -> None` <small>(L71)</small>


---

#### `def get_agent_logger() -> AgentLogger` <small>(L81)</small>


---

#### `def set_verbose(verbose: bool) -> None` <small>(L88)</small>


---

#### `def reset_agent_logger() -> None` <small>(L92)</small>



---

## `aki.agent.orchestrator`

**文件路径：** `aki/agent/orchestrator.py`

Agent Orchestrator

Manages multi-agent collaboration, including:
- Task dispatch to the main agent
- Depth and count limit enforcement
- Agent lifecycle management
---

#### class `OrchestratorConfig(BaseModel)`

```
Orchestrator configuration.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `max_agents_per_task` | `int` | `5` | Maximum number of agents allowed per task |
| `max_agent_depth` | `int` | `3` | Maximum agent call chain depth |
| `max_iterations` | `int` | `10` | Maximum iterations per agent |
| `default_agent_type` | `str` | `'main'` | Default agent type for task execution |


---

#### class `AgentOrchestrator`

```
Agent Orchestrator.

Entry point for running tasks with the multi-agent system.
Manages agent lifecycle and enforces resource limits.
```

**方法：**

##### `def __init__(self, config: Optional[OrchestratorConfig] = None, llm: Optional[LLMInterface] = None, memory: Optional[Any] = None, tools: Optional[list[BaseTool]] = None, auto_load_tools: bool = True)` <small>(L60)</small>

Initialize the orchestrator.

Args:
    config: Orchestrator configuration
    llm: LLM interface for agents
    memory: Memory manager for agents
    tools: List of tools to provide to agents
    auto_load_tools: Automatically load all registered tools

##### `async def run_task(self, task: str, agent_type: Optional[str] = None) -> Any` <small>(L132)</small>

Execute a task with the multi-agent system.

This is the main entry point for task execution.

Args:
    task: Task description
    agent_type: Agent type to use (defaults to config.default_agent_type)

Returns:
    Result from the agent execution

##### `def create_session_agent(self, role: Optional[Any] = None) -> tuple[UniversalAgent, AgentContext]` <small>(L219)</small>

Create a persistent agent + context for multi-turn sessions.

Unlike ``run_task()`` which creates a throwaway agent per task, this
returns an agent that should be kept alive across conversation turns
and driven via ``agent.run_turn()``.

Returns:
    (agent, context) tuple — caller is responsible for keeping these
    alive for the duration of the session.

##### `def get_active_agent_count(self, task_id: str) -> int` <small>(L276)</small>

Get the number of active agents for a task.

##### `def get_active_task_count(self) -> int` <small>(L280)</small>

Get the number of active tasks.

##### `async def cancel_task(self, task_id: str) -> None` <small>(L284)</small>

Cancel a running task.

Args:
    task_id: Task ID to cancel

##### `def set_llm(self, llm: LLMInterface) -> None` <small>(L294)</small>

Set the LLM interface.

##### `def set_memory(self, memory: Any) -> None` <small>(L298)</small>

Set the memory manager.


---

#### `def get_orchestrator() -> AgentOrchestrator` <small>(L307)</small>

Get the global orchestrator instance (singleton).


---

#### `def reset_orchestrator() -> None` <small>(L315)</small>

Reset the global orchestrator instance (useful for testing).



---

## `aki.agent.roles` *(deprecated)*

**文件路径：** `aki/agent/roles.py`

> **Deprecated stub.** Roles have been removed — personality now drives agent identity.
> All agents have full tool access; there is no `allowed_tools` restriction.
> This module is retained only for backward-compatibility imports.



---

## `aki.agent.state`

**文件路径：** `aki/agent/state.py`

Agent Context

Tracks the call chain depth and resource limits for spawned agents.
AgentState has been removed — the native tool calling loop manages iteration internally.
---

#### class `AgentContext(BaseModel)`

```
Agent execution context.

Passed to child agents to track depth and enforce resource limits.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `task_id` | `str` | `` | Unique identifier for the task |
| `depth` | `int` | `0` | Current depth in the agent call chain (0 = root agent) |
| `parent_agent_id` | `Optional[str]` | `None` | ID of the parent agent (None for root) |
| `max_depth` | `int` | `3` | Maximum allowed depth (prevents infinite recursion) |
| `active_agents` | `int` | `0` | Number of currently active agents in this task |
| `max_agents` | `int` | `5` | Maximum number of agents allowed per task |
| `workspace_dir` | `Optional[str]` | `None` | Absolute path to the workspace directory for outputting intermediate files |
| `agent_identity` | `Optional[Any]` | `None` | AgentIdentity for persistent agent instances (Phase 3) |
| `shared_memory` | `Optional[Any]` | `None` | SharedTaskMemory instance for inter-agent communication (Phase 3) |

**方法：**

##### `def can_spawn(self) -> bool` <small>(L60)</small>

Check if spawning a new agent is allowed.

##### `def create_child_context(self, parent_id: str) -> 'AgentContext'` <small>(L64)</small>

Create a context for a child agent.



---

## `aki.agent.types`

**文件路径：** `aki/agent/types.py`

Agent Action Types — DEPRECATED

This module is kept as a stub for backward compatibility.
The ReACT loop and manual action types have been removed in favour of native tool calling.

---

## `aki.agent.communication.addressing`

**文件路径：** `aki/agent/communication/addressing.py`

Agent Addressing

Parses and resolves pipeline-style agent addresses.
Format: [project:]agent_name[:instance]
---

#### class `AgentAddress`

```
Parses and resolves pipeline-style agent addresses.

Address format: ``[project:]agent_name[:instance]``

Examples:
    - ``"Localizer"`` — matches any Localizer agent
    - ``"translation:Localizer"`` — matches Localizer in the "translation" project
    - ``"task_abc:MediaExtractor:0"`` — matches specific instance 0
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|

**方法：**

##### `def __init__(self, project: Optional[str], agent_name: str, instance: Optional[str]) -> None` <small>(L26)</small>

##### `def parse(cls, address: str) -> 'AgentAddress'` <small>(L32)</small>

Parse an address string into components.

Args:
    address: Address string like "project:agent_name:instance", "agent_name:instance", or "agent_name".

Returns:
    AgentAddress with parsed components.

##### `def matches(self, pattern: str) -> bool` <small>(L50)</small>

Check if this address matches a pattern.

Pattern components use glob matching. Missing components in the
pattern are treated as wildcards.

Args:
    pattern: Address pattern to match against.

Returns:
    True if this address matches the pattern.

##### `def __repr__(self) -> str` <small>(L94)</small>



---

## `aki.agent.communication.bus`

**文件路径：** `aki/agent/communication/bus.py`

Agent Bus

Central message bus for agent-to-agent communication.
Supports direct messaging, address-pattern routing, and broadcast events.
---

#### class `AgentBus`

```
Central message bus for inter-agent communication.

Supports:
- Direct messaging (agent_id -> agent_id)
- Address-pattern routing (project:role -> matching agents)
- Broadcast events to subscribers
- Async mailbox per agent with timeout-based receive

Usage::

    bus = AgentBus()
    bus.register_agent("agent-1", "translation:MediaExtractor")
    bus.register_agent("agent-2", "translation:Localizer")

    await bus.send(AgentMessage(sender="agent-1", recipient="translation:Localizer", content="done"))
    msg = await bus.receive("agent-2", timeout=5.0)
```

**方法：**

##### `def __init__(self) -> None` <small>(L39)</small>

##### `def register_agent(self, agent_id: str, address: str) -> None` <small>(L49)</small>

Register an agent on the bus.

Args:
    agent_id: Unique agent instance ID.
    address: Pipeline address (e.g. "translation:Localizer:0").

##### `def unregister_agent(self, agent_id: str) -> None` <small>(L62)</small>

Remove an agent from the bus.

##### `async def send(self, message: AgentMessage) -> int` <small>(L75)</small>

Send a message to one or more agents.

The recipient field can be:
- An agent_id (direct delivery)
- An address pattern (delivered to all matching agents)

Args:
    message: The message to send.

Returns:
    Number of agents the message was delivered to.

##### `async def receive(self, agent_id: str, timeout: float = 30.0) -> Optional[AgentMessage]` <small>(L108)</small>

Receive the next message for an agent.

Blocks until a message arrives or timeout is reached.

Args:
    agent_id: The agent to receive for.
    timeout: Maximum wait time in seconds.

Returns:
    AgentMessage if received, None on timeout.

##### `def peek(self, agent_id: str) -> int` <small>(L135)</small>

Check how many messages are waiting in an agent's mailbox.

##### `async def broadcast(self, event: AgentEvent) -> None` <small>(L140)</small>

Broadcast an event to all subscribed agents.

Handlers are called concurrently but errors are logged and swallowed.

##### `def subscribe(self, agent_id: str, event_name: str, handler: Callable) -> None` <small>(L157)</small>

Subscribe to broadcast events.

Args:
    agent_id: The subscribing agent's ID.
    event_name: Event name to subscribe to.
    handler: Async callable(AgentEvent) -> None.

##### `def get_registered_agents(self) -> dict[str, str]` <small>(L173)</small>

Return a copy of agent_id -> address mapping.



---

## `aki.agent.communication.messages`

**文件路径：** `aki/agent/communication/messages.py`

Agent Message Types

Defines the message and event types used for inter-agent communication.
---

#### class `AgentMessage(BaseModel)`

```
Peer-to-peer message between agents.

Supports request/response pairing via correlation_id.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `id` | `str` | `` |  |
| `sender` | `str` | `` | Sender agent_id or address |
| `recipient` | `str` | `` | Recipient agent_id or address pattern (e.g.  |
| `content` | `Any` | `None` | Message payload |
| `message_type` | `str` | `'request'` | Message type:  |
| `correlation_id` | `Optional[str]` | `None` | Links a response to its original request |
| `timestamp` | `datetime` | `` |  |

**方法：**

##### `def create_response(self, content: Any) -> 'AgentMessage'` <small>(L35)</small>

Create a response message to this request.


---

#### class `AgentEvent(BaseModel)`

```
Broadcast event for coordination.

Published to all agents subscribed to the event_name.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `source` | `str` | `` | Source agent_id |
| `event_name` | `str` | `` | Event identifier (e.g.  |
| `payload` | `dict[str, Any]` | `` |  |
| `timestamp` | `datetime` | `` |  |



---

