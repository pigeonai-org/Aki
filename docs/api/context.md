# `aki.context` API 文档

> Context 管理子系统 — Token 预算追踪、自动压缩策略链

---

## `aki.context.budget`

**文件路径：** `aki/context/budget.py`

Token Budget

Tracks token allocation and remaining capacity for an agent's conversation.
---

#### class `TokenBudget(BaseModel)`

```
Token budget for a single agent conversation.

Tracks how much context space is available after accounting for
system prompt, tool schemas, and a reserve buffer.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `max_context_tokens` | `int` | `128000` | Model |
| `system_prompt_tokens` | `int` | `0` | Tokens used by system prompt |
| `tool_schemas_tokens` | `int` | `0` | Tokens used by tool definitions |
| `reserve_tokens` | `int` | `4000` | Buffer reserved for model output |
| `used_message_tokens` | `int` | `0` | Tokens currently used by messages |

**方法：**

##### `def available_tokens(self) -> int` <small>(L25)</small>

Tokens available for conversation messages.

##### `def total_used(self) -> int` <small>(L37)</small>

Total tokens consumed across all categories.

##### `def utilization(self) -> float` <small>(L42)</small>

Fraction of context window used (0.0 to 1.0).

##### `def has_capacity(self) -> bool` <small>(L48)</small>

Check if there is remaining capacity for more messages.

##### `def update_message_tokens(self, tokens: int) -> None` <small>(L52)</small>

Set the current message token count.

##### `def compaction_threshold(self) -> int` <small>(L57)</small>

Token count at which compaction should trigger (75% of message budget).



---

## `aki.context.manager`

**文件路径：** `aki/context/manager.py`

Context Manager

Manages token budget and automatic compaction for agent conversations.
Replaces the hardcoded 20-iteration cap with intelligent context management.
---

#### class `ContextManager`

```
Manages token budget for agent conversations.

Tracks token usage, detects when compaction is needed, and applies
a chain of compaction strategies to keep the context within limits.

Usage::

    ctx = ContextManager(max_context_tokens=128_000)
    budget = ctx.allocate_budget(system_prompt_tokens=2000, tool_schemas_tokens=1500)

    # During agent loop:
    if ctx.needs_compaction(messages):
        messages = await ctx.compact(messages, llm)
```

**方法：**

##### `def __init__(self, max_context_tokens: int = 128000, strategies: list[CompactionStrategy] | None = None, token_counter: TokenCounter | None = None, max_compaction_failures: int = 3) -> None` <small>(L47)</small>

##### `def estimate_tokens(self, messages: list[dict[str, Any]]) -> int` <small>(L60)</small>

Estimate total tokens for a list of messages.

##### `def allocate_budget(self, system_prompt_tokens: int = 0, tool_schemas_tokens: int = 0, reserve_tokens: int = 4000) -> TokenBudget` <small>(L64)</small>

Create a token budget for this conversation.

Args:
    system_prompt_tokens: Tokens consumed by the system prompt.
    tool_schemas_tokens: Tokens consumed by tool definitions.
    reserve_tokens: Buffer reserved for model output.

Returns:
    TokenBudget tracking capacity and usage.

##### `def needs_compaction(self, messages: list[dict[str, Any]], budget: Optional[TokenBudget] = None) -> bool` <small>(L88)</small>

Check if the message list needs compaction.

Uses the budget's compaction threshold if provided, otherwise uses
75% of max_context_tokens as the threshold.

##### `async def compact(self, messages: list[dict[str, Any]], llm: Optional[Any] = None, budget: Optional[TokenBudget] = None) -> list[dict[str, Any]]` <small>(L104)</small>

Apply compaction strategies in chain until context fits.

Strategies are tried in order. After each strategy, token count
is re-evaluated. Stops as soon as the context fits within budget.

Args:
    messages: Current conversation messages.
    llm: Optional LLM for summarization strategy.
    budget: Optional budget for threshold calculation.

Returns:
    Compacted message list.

##### `def reset_circuit_breaker(self) -> None` <small>(L162)</small>

Reset the compaction failure counter.



---

## `aki.context.strategies`

**文件路径：** `aki/context/strategies.py`

Compaction Strategies

Pluggable strategies for reducing conversation context size when approaching token limits.
---

#### class `CompactionStrategy(ABC)`

```
Base class for context compaction strategies.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `str` | `'base'` |  |

**方法：**

##### `async def compact(self, messages: list[dict[str, Any]], budget: TokenBudget, llm: Optional[Any] = None) -> list[dict[str, Any]]` <small>(L23)</small>

Compact messages to fit within budget.

Args:
    messages: Current conversation messages.
    budget: Token budget with capacity info.
    llm: Optional LLM interface (needed by summarize strategy).

Returns:
    Compacted message list.


---

#### class `TruncateStrategy(CompactionStrategy)`

```
Drop the oldest messages, keeping the most recent ones.

Always preserves the system message (index 0) and at least ``keep_recent``
messages from the tail.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'truncate'` |  |

**方法：**

##### `def __init__(self, keep_recent: int = 10) -> None` <small>(L53)</small>

##### `async def compact(self, messages: list[dict[str, Any]], budget: TokenBudget, llm: Optional[Any] = None) -> list[dict[str, Any]]` <small>(L56)</small>


---

#### class `StripMediaStrategy(CompactionStrategy)`

```
Replace large tool results with compact summaries.

Scans for tool result messages whose content exceeds ``max_result_chars``
and replaces them with a truncated preview.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'strip_media'` |  |

**方法：**

##### `def __init__(self, max_result_chars: int = 2000) -> None` <small>(L89)</small>

##### `async def compact(self, messages: list[dict[str, Any]], budget: TokenBudget, llm: Optional[Any] = None) -> list[dict[str, Any]]` <small>(L92)</small>


---

#### class `SummarizeOldStrategy(CompactionStrategy)`

```
Use the LLM to summarize older messages into a concise synopsis.

Keeps the system message and recent messages intact, replaces everything
in between with an LLM-generated summary.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'summarize_old'` |  |

**方法：**

##### `def __init__(self, keep_recent: int = 6) -> None` <small>(L130)</small>

##### `async def compact(self, messages: list[dict[str, Any]], budget: TokenBudget, llm: Optional[Any] = None) -> list[dict[str, Any]]` <small>(L133)</small>



---

## `aki.context.token_counter`

**文件路径：** `aki/context/token_counter.py`

Token Counter

Estimates token counts for messages using tiktoken (if available) or a heuristic fallback.
---

#### class `TokenCounter`

```
Counts tokens in text or message lists.

Uses tiktoken when available, otherwise falls back to a character-based heuristic.
```

**方法：**

##### `def count_text(self, text: str) -> int` <small>(L37)</small>

Count tokens in a plain text string.

##### `def count_message(self, message: dict[str, Any]) -> int` <small>(L45)</small>

Count tokens in a single chat message.

Accounts for role overhead (~4 tokens) and content.

##### `def count_messages(self, messages: list[dict[str, Any]]) -> int` <small>(L67)</small>

Count total tokens across a list of messages.



---

