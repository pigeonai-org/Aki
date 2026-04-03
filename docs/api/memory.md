# `aki.memory` API 文档

> 记忆系统 — 短期/长期记忆存储、任务间共享状态、滑动窗口策略

---

## `aki.memory.base`

**文件路径：** `aki/memory/base.py`

Memory Base Classes

Memory system for storing and retrieving agent memories.
Separate from Knowledge (static domain knowledge) - Memory is for dynamic session data.
---

#### class `MemoryItem(BaseModel)`

```
A single memory unit.

Stores observations, actions, results, and thoughts from agent execution.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `id` | `str` | `` | Unique identifier for this memory |
| `content` | `str` | `` | Memory content |
| `type` | `str` | `MemoryCategory.TASK_EVENT.value` | Legacy memory type label retained for backward compatibility |
| `category` | `MemoryCategory` | `MemoryCategory.TASK_EVENT` | Canonical memory category |
| `scope` | `MemoryScope` | `MemoryScope.SHORT_TERM` | Memory scope: short_term or long_term |
| `timestamp` | `datetime` | `` | When this memory was created |
| `metadata` | `dict[str, Any]` | `` | Additional metadata |
| `importance` | `float` | `0.5` | Importance score for filtering (0.0-1.0) |
| `agent_id` | `Optional[str]` | `None` | ID of the agent that created this memory |
| `task_id` | `Optional[str]` | `None` | ID of the task this memory belongs to |
| `namespace` | `str` | `'default'` | Namespace identifier for long-term memory separation |
| `expires_at` | `Optional[datetime]` | `None` | Optional expiry timestamp (mainly for long-term memory) |
| `source_uri` | `Optional[str]` | `None` | Optional source URI, usually for web/domain memory |
| `fingerprint` | `Optional[str]` | `None` | Stable fingerprint used for deduplication/upsert |


---

#### class `MemoryStrategy(ABC)`

```
Abstract base class for memory selection strategies.

Strategies determine which memories to keep/return when limits are reached.
```

**方法：**

##### `def select(self, memories: list[MemoryItem], limit: int) -> list[MemoryItem]` <small>(L114)</small>

Select memories to keep/return.

Args:
    memories: All available memories
    limit: Maximum number to return

Returns:
    Selected memories


---

#### class `MemoryStore(ABC)`

```
Abstract base class for memory storage.

Implementations can use in-memory, file, or database storage.
```

**方法：**

##### `async def add(self, item: MemoryItem) -> None` <small>(L140)</small>

Add a memory item to the store.

Args:
    item: Memory to add

##### `async def get_recent(self, n: int) -> list[MemoryItem]` <small>(L150)</small>

Get the N most recent memories.

Args:
    n: Number of memories to retrieve

Returns:
    List of recent memories

##### `async def search(self, query: str, limit: int = 10) -> list[MemoryItem]` <small>(L163)</small>

Search memories by query.

Args:
    query: Search query
    limit: Maximum results

Returns:
    Matching memories

##### `async def search_semantic(self, query: MemoryQuery) -> list[MemoryItem]` <small>(L180)</small>

Optional semantic search interface.

Stores that don't support semantic scoring should override this as needed.
Default behavior falls back to keyword search.

##### `async def get_by_task(self, task_id: str) -> list[MemoryItem]` <small>(L195)</small>

Get all memories for a task.

Args:
    task_id: Task ID

Returns:
    Memories for the task

##### `async def clear(self) -> None` <small>(L208)</small>

Clear all memories.

##### `async def count(self) -> int` <small>(L213)</small>

Get total memory count.

##### `async def prune_expired(self, now: Optional[datetime] = None) -> int` <small>(L217)</small>

Optional TTL pruning hook.

Returns:
    Number of records removed.



---

## `aki.memory.manager`

**文件路径：** `aki/memory/manager.py`

Memory Manager

Coordinates short-term and long-term memory stores with explicit policies for:
- task-scoped short-term working memory
- semantic long-term memory for user/domain/web knowledge
---

#### class `MemoryManager`

```
Memory manager with policy-aware routing between short-term and long-term stores.
```

**方法：**

##### `def __init__(self, short_term: Optional[MemoryStore] = None, long_term: Optional[MemoryStore] = None, strategy: Optional[MemoryStrategy] = None, window_size: int = 20, default_namespace: str = 'default', short_term_observe_limit: int = 12, long_term_top_k: int = 6, long_term_min_score: float = 0.0, web_ttl_days: Optional[int] = 30, domain_ttl_days: Optional[int] = None, user_instruction_ttl_days: Optional[int] = None)` <small>(L32)</small>

##### `async def remember(self, content: str, type: str, task_id: Optional[str] = None, agent_id: Optional[str] = None, importance: float = 0.5, **metadata: Any) -> MemoryItem` <small>(L138)</small>

Backward-compatible API: remember into short-term memory.

##### `async def remember_short_term(self, content: str, **metadata: Any) -> MemoryItem` <small>(L159)</small>

Persist memory to short-term task-scoped storage.

##### `async def remember_long_term(self, content: str, **metadata: Any) -> MemoryItem` <small>(L204)</small>

Persist semantic memory for long-term retrieval.

##### `async def upsert_user_instruction(self, key: str, content: str, **metadata: Any) -> MemoryItem` <small>(L267)</small>

Upsert user instruction memory with stable fingerprinting.

##### `async def recall(self, query: Optional[str] = None, limit: int = 10, task_id: Optional[str] = None) -> list[MemoryItem]` <small>(L295)</small>

Backward-compatible API: recall from short-term memory.

##### `async def recall_short_term(self) -> list[MemoryItem]` <small>(L306)</small>

Recall task-scoped short-term memory.

##### `async def recall_long_term(self) -> list[MemoryItem]` <small>(L345)</small>

Recall semantic long-term memory.

##### `async def recall_context(self) -> dict[str, list[MemoryItem]]` <small>(L391)</small>

Retrieve fused memory context for an agent observation.

##### `async def promote(self) -> int` <small>(L447)</small>

Promote selected short-term memories to long-term storage.

##### `async def consolidate(self) -> int` <small>(L492)</small>

Backward-compatible alias of promote().

##### `async def prune_long_term(self, now: Optional[datetime] = None) -> int` <small>(L498)</small>

Prune expired long-term memories by TTL policy.

##### `async def clear_short_term(self) -> None` <small>(L509)</small>

Clear short-term memory.

##### `async def clear_all(self) -> None` <small>(L513)</small>

Clear short-term and long-term memory.

##### `async def get_stats(self) -> dict[str, Any]` <small>(L519)</small>

Get memory statistics.


---

#### `def get_memory_manager() -> MemoryManager` <small>(L535)</small>

Get the global memory manager instance (singleton).


---

#### `def reset_memory_manager() -> None` <small>(L543)</small>

Reset the global memory manager instance (useful for testing).



---

## `aki.memory.migration`

**文件路径：** `aki/memory/migration.py`

Memory migration utilities.

Provides helpers for migrating legacy JSON-based memory snapshots into
the new long-term semantic memory store.
---

#### `async def migrate_legacy_json_to_long_term(memory_manager: MemoryManager, source_file: str) -> dict[str, Any]` <small>(L59)</small>

Migrate legacy JSON memory file into long-term memory.

Expected file format: list[dict] where each dict can be parsed by MemoryItem.



---

## `aki.memory.shared`

**文件路径：** `aki/memory/shared.py`

Shared Task Memory

In-memory key-value store shared between agents working on the same task.
Replaces the hacky _last_media_extractor_output / _last_localized_output
instance variables in DelegateToWorkerTool.
---

#### class `SharedTaskMemory`

```
Shared state between agents working on the same task.

Each task gets an isolated namespace keyed by task_id.
Thread-safe via asyncio.Lock per task.

Usage::

    shared = SharedTaskMemory()

    # Agent 1 stores transcription result
    await shared.set("task_abc", "transcription", {"segments": [...]})

    # Agent 2 reads it
    transcription = await shared.get("task_abc", "transcription")

    # Cleanup when task is done
    await shared.clear_task("task_abc")
```

**方法：**

##### `def __init__(self) -> None` <small>(L38)</small>

##### `async def get(self, task_id: str, key: str, default: Any = None) -> Any` <small>(L42)</small>

Get a value from the task's shared state.

Args:
    task_id: The task identifier.
    key: The state key.
    default: Value to return if key is not found.

Returns:
    The stored value, or default if not found.

##### `async def set(self, task_id: str, key: str, value: Any) -> None` <small>(L57)</small>

Set a value in the task's shared state.

Args:
    task_id: The task identifier.
    key: The state key.
    value: The value to store.

##### `async def get_all(self, task_id: str) -> dict[str, Any]` <small>(L70)</small>

Get all key-value pairs for a task.

##### `async def has(self, task_id: str, key: str) -> bool` <small>(L75)</small>

Check if a key exists in the task's shared state.

##### `async def delete(self, task_id: str, key: str) -> bool` <small>(L80)</small>

Delete a key from the task's shared state.

Returns:
    True if the key existed, False otherwise.

##### `async def keys(self, task_id: str) -> list[str]` <small>(L93)</small>

List all keys in the task's shared state.

##### `async def clear_task(self, task_id: str) -> None` <small>(L98)</small>

Remove all shared state for a task.

##### `async def update(self, task_id: str, data: dict[str, Any]) -> None` <small>(L105)</small>

Merge multiple key-value pairs into the task's shared state.

Args:
    task_id: The task identifier.
    data: Dict of key-value pairs to merge.

##### `def active_tasks(self) -> list[str]` <small>(L117)</small>

List task_ids with active shared state.



---

## `aki.memory.types`

**文件路径：** `aki/memory/types.py`

Memory typing helpers.

Defines canonical memory scopes/categories and common query parameters.
---

#### class `MemoryScope(str, Enum)`

```
Scope for a memory record.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `SHORT_TERM` | `` | `'short_term'` |  |
| `LONG_TERM` | `` | `'long_term'` |  |


---

#### class `MemoryCategory(str, Enum)`

```
Canonical memory category values.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `TASK_EVENT` | `` | `'task_event'` |  |
| `MULTIMODAL_ARTIFACT` | `` | `'multimodal_artifact'` |  |
| `USER_INSTRUCTION` | `` | `'user_instruction'` |  |
| `DOMAIN_KNOWLEDGE` | `` | `'domain_knowledge'` |  |
| `WEB_KNOWLEDGE` | `` | `'web_knowledge'` |  |
| `OBSERVATION` | `` | `'observation'` |  |
| `ACTION` | `` | `'action'` |  |
| `RESULT` | `` | `'result'` |  |
| `THOUGHT` | `` | `'thought'` |  |


---

#### `def normalize_category(value: Optional[str | MemoryCategory]) -> MemoryCategory` <small>(L45)</small>

Normalize arbitrary category strings into canonical enum values.


---

#### `def normalize_scope(value: Optional[str | MemoryScope]) -> MemoryScope` <small>(L63)</small>

Normalize scope strings into canonical enum values.


---

#### class `MemoryQuery(BaseModel)`

```
Structured query object for memory retrieval.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `query` | `Optional[str]` | `None` | Semantic/keyword query |
| `limit` | `int` | `10` | Maximum number of memories to return |
| `task_id` | `Optional[str]` | `None` | Restrict search to a task id |
| `namespace` | `str` | `'default'` | Namespace for long-term memory |
| `categories` | `Optional[set[MemoryCategory]]` | `None` | Filter by memory categories |
| `scope` | `Optional[MemoryScope]` | `None` | Target memory scope |
| `min_score` | `float` | `0.0` | Minimum relevance score |
| `include_expired` | `bool` | `False` | Whether to include expired long-term memory items |
| `now` | `Optional[datetime]` | `None` | Reference time for expiry filtering |



---

## `aki.memory.stores.long_term`

**文件路径：** `aki/memory/stores/long_term.py`

Long-Term Memory Store

File-based persistent storage for memories across sessions.
Uses JSON for simplicity - can be upgraded to database later.
---

#### class `LongTermMemoryStore(MemoryStore)`

```
File-based long-term memory store.

Persists memories to JSON files for durability.
Simple implementation for MVP - consider SQLite/PostgreSQL for production.
```

**方法：**

##### `def __init__(self, persist_dir: str = './data/memory')` <small>(L25)</small>

Initialize the store.

Args:
    persist_dir: Directory for memory files

##### `async def add(self, item: MemoryItem) -> None` <small>(L73)</small>

Add a memory to the store.

##### `async def get_recent(self, n: int) -> list[MemoryItem]` <small>(L89)</small>

Get the N most recent memories.

##### `async def search(self, query: str, limit: int = 10) -> list[MemoryItem]` <small>(L99)</small>

Simple keyword search in memory content.

##### `async def search_semantic(self, query: MemoryQuery) -> list[MemoryItem]` <small>(L123)</small>

Fallback structured retrieval for stores without vector search.

##### `async def get_by_task(self, task_id: str) -> list[MemoryItem]` <small>(L151)</small>

Get all memories for a task.

##### `async def get_by_id(self, memory_id: str) -> Optional[MemoryItem]` <small>(L156)</small>

Get a memory by ID.

##### `async def clear(self) -> None` <small>(L164)</small>

Clear all memories.

##### `async def count(self) -> int` <small>(L171)</small>

Get total memory count.

##### `async def prune_expired(self, now: Optional[datetime] = None) -> int` <small>(L176)</small>

Remove expired memories and persist the change.



---

## `aki.memory.stores.short_term`

**文件路径：** `aki/memory/stores/short_term.py`

Short-Term Memory Store

In-memory storage for current session memories.
Fast but not persistent across restarts.
---

#### class `ShortTermMemoryStore(MemoryStore)`

```
In-memory short-term memory store.

Stores memories in a list for fast access.
Not persistent - cleared when the process ends.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|

**方法：**

##### `def __init__(self, max_size: int = 5000, max_items_per_task: int = 300)` <small>(L26)</small>

Initialize the store.

Args:
    max_size: Maximum number of memories across all tasks
    max_items_per_task: Maximum number of memories per task

##### `async def add(self, item: MemoryItem) -> None` <small>(L88)</small>

Add a memory to the store.

##### `async def get_recent(self, n: int) -> list[MemoryItem]` <small>(L99)</small>

Get the N most recent memories.

##### `async def search(self, query: str, limit: int = 10) -> list[MemoryItem]` <small>(L105)</small>

Simple keyword search in memory content.

For production, consider using vector similarity search.

##### `async def get_by_task(self, task_id: str) -> list[MemoryItem]` <small>(L128)</small>

Get all memories for a task.

##### `async def get_by_id(self, memory_id: str) -> Optional[MemoryItem]` <small>(L136)</small>

Get a memory by ID.

##### `async def recall(self, query: MemoryQuery) -> list[MemoryItem]` <small>(L140)</small>

Structured retrieval with task/category filters.

##### `async def clear(self) -> None` <small>(L162)</small>

Clear all memories.

##### `async def count(self) -> int` <small>(L169)</small>

Get total memory count.



---

## `aki.memory.strategies.sliding_window`

**文件路径：** `aki/memory/strategies/sliding_window.py`

Sliding Window Memory Strategy

Simple strategy that keeps the N most recent memories.
---

#### class `SlidingWindowStrategy(MemoryStrategy)`

```
Sliding window memory strategy.

Keeps the most recent memories up to a window size.
Simple but effective for short-term memory management.
```

**方法：**

##### `def __init__(self, window_size: int = 20)` <small>(L18)</small>

Initialize the strategy.

Args:
    window_size: Maximum number of memories to keep

##### `def select(self, memories: list[MemoryItem], limit: int) -> list[MemoryItem]` <small>(L27)</small>

Select the most recent memories.

Args:
    memories: All available memories
    limit: Maximum number to return (overrides window_size if smaller)

Returns:
    Most recent memories up to the limit



---

