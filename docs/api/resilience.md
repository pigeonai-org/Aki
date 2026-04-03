# `aki.resilience` API 文档

> 弹性恢复子系统 — 指数退避、模型 Failover、错误分类与自动恢复

---

## `aki.resilience.backoff`

**文件路径：** `aki/resilience/backoff.py`

Rate Limit Backoff

Exponential backoff with jitter for rate-limited API requests.
---

#### class `RateLimitBackoff`

```
Retries an async operation with exponential backoff and jitter.

Usage::

    backoff = RateLimitBackoff(base_delay=1.0, max_delay=60.0, max_retries=5)
    result = await backoff.execute_with_retry(llm.chat, messages, tools=tools)
```

**方法：**

##### `def __init__(self, base_delay: float = 1.0, max_delay: float = 60.0, max_retries: int = 5, jitter: float = 0.5) -> None` <small>(L27)</small>

##### `async def execute_with_retry(self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T` <small>(L45)</small>

Execute an async function with retry logic.

Args:
    func: The async callable to execute.
    *args: Positional arguments for func.
    retryable_exceptions: Tuple of exception types to retry on.
    **kwargs: Keyword arguments for func.

Returns:
    The result of func.

Raises:
    The last exception if all retries are exhausted.



---

## `aki.resilience.failover`

**文件路径：** `aki/resilience/failover.py`

Model Failover

Wraps LLMInterface with automatic provider failover on errors.
Transparently switches to the next model in the chain when a provider fails.
---

#### class `FailoverChain(BaseModel)`

```
Ordered list of model identifiers to try.

Example::

    chain = FailoverChain(models=[
        "anthropic:claude-sonnet-4-20250514",
        "openai:gpt-4o",
        "google:gemini-2.0-flash",
    ])
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `models` | `list[str]` | `` | Ordered model identifiers (provider:model_name) |


---

#### class `ModelFailover(BaseModelInterface)`

```
LLMInterface wrapper that automatically fails over to the next provider.

IS-A BaseModelInterface, so it can be used anywhere an LLM is expected.
Wraps multiple LLM instances and tries them in order until one succeeds.

Usage::

    from aki.models.registry import ModelRegistry

    chain = FailoverChain(models=["anthropic:claude-sonnet-4-20250514", "openai:gpt-4o"])
    failover = ModelFailover(chain, model_factory=ModelRegistry.create_llm)
    response = await failover.chat(messages)
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `model_type` | `` | `ModelType.LLM` |  |

**方法：**

##### `def __init__(self, chain: FailoverChain, model_factory: Any = None, settings: Any = None) -> None` <small>(L56)</small>

Args:
    chain: Failover chain of model identifiers.
    model_factory: Callable(model_string) -> LLMInterface.
                   If None, models must be set via set_models().
    settings: Application settings for API key resolution.

##### `def set_models(self, models: list[Any]) -> None` <small>(L94)</small>

Directly set pre-created LLM instances (for testing or manual setup).

##### `async def chat(self, messages: list[dict[str, Any]], tools: Optional[list[dict[str, Any]]] = None, temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs: Any) -> ModelResponse` <small>(L98)</small>

Chat with automatic failover.

Tries each model in the chain. On failure, logs the error and
advances to the next provider.

##### `async def invoke(self, **kwargs: Any) -> ModelResponse` <small>(L145)</small>

Invoke via chat interface.

##### `async def stream(self, **kwargs: Any) -> AsyncIterator[str]` <small>(L150)</small>

Streaming failover - tries current model's stream method.

##### `def current_model(self) -> str` <small>(L158)</small>

The model identifier currently in use.

##### `def reset(self) -> None` <small>(L164)</small>

Reset to the first (preferred) model in the chain.



---

## `aki.resilience.recovery`

**文件路径：** `aki/resilience/recovery.py`

Error Recovery Handler

Circuit-breaker style error recovery for the agent execution loop.
Maps exception types to recovery actions.
---

#### class `RecoveryAction(str, Enum)`

```
Actions the agent loop can take in response to an error.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `COMPACT` | `` | `'compact'` |  |
| `RETRY_BACKOFF` | `` | `'retry_backoff'` |  |
| `FAILOVER` | `` | `'failover'` |  |
| `CONTINUE` | `` | `'continue'` |  |
| `ABORT` | `` | `'abort'` |  |


---

#### class `RecoveryResult`

```
Recovery decision with optional context.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|

**方法：**

##### `def __init__(self, action: RecoveryAction, message: str = '', data: Any = None) -> None` <small>(L30)</small>


---

#### class `ErrorRecoveryHandler`

```
Maps exceptions to recovery actions for the agent loop.

The agent loop wraps its LLM calls in try/except and delegates to
this handler to decide what to do next.

Usage::

    handler = ErrorRecoveryHandler(context_manager=ctx_mgr)
    try:
        response = await llm.chat(messages, tools=tools)
    except Exception as e:
        result = handler.handle_error(e, messages)
        if result.action == RecoveryAction.COMPACT:
            messages = await ctx_mgr.compact(messages, llm)
        elif result.action == RecoveryAction.ABORT:
            break
```

**方法：**

##### `def __init__(self, context_manager: Optional[Any] = None, failover: Optional[Any] = None, max_consecutive_errors: int = 3) -> None` <small>(L56)</small>

##### `def handle_error(self, error: Exception, messages: list[dict[str, Any]] | None = None) -> RecoveryResult` <small>(L67)</small>

Determine recovery action for an error.

Args:
    error: The exception that occurred.
    messages: Current message list (for context-aware decisions).

Returns:
    RecoveryResult with the recommended action.

##### `def record_success(self) -> None` <small>(L125)</small>

Record a successful operation (resets the consecutive error counter).



---

