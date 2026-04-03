# `aki.config` API 文档

> 全局配置 — Pydantic Settings，支持环境变量和 .env 文件

---

## `aki.config.settings`

**文件路径：** `aki/config/settings.py`

Aki Global Configuration

Centralized configuration management using Pydantic Settings.
Supports environment variables and .env files.
---

#### class `AgentSettings(BaseSettings)`

```
Agent system configuration.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `max_agents_per_task` | `int` | `5` | Maximum number of agents allowed per task |
| `max_agent_depth` | `int` | `3` | Maximum agent call chain depth (prevents infinite recursion) |
| `agents_dir` | `str` | `'.aki/agents'` | Directory for agent definition files (agent.md frontmatter) |
| `model_config` | `` | `SettingsConfigDict(env_prefix='AKI_')` |  |


---

#### class `MemorySettings(BaseSettings)`

```
Memory system configuration.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `window_size` | `int` | `20` | Sliding window size used by short-term selection strategy |
| `short_term_max_items_per_task` | `int` | `300` | Maximum short-term memory items retained per task |
| `short_term_observe_limit` | `int` | `12` | Default number of short-term memories injected into observations |
| `default_namespace` | `str` | `'default'` | Default namespace for memory partitioning |
| `long_term_memory_dir` | `str` | `'.aki/long-term-memory'` | Directory for human-readable long-term memory .md files |
| `memory_review_enabled` | `bool` | `True` | Run a post-turn memory review pass after each agent response |
| `session_dir` | `str` | `'.aki/sessions'` | Directory for session persistence |
| `memory_base_dir` | `str` | `'.aki/memory'` | Base directory for all memory stores |
| `review_enabled` | `bool` | `True` | Enable the post-turn memory review pass |
| `model_config` | `` | `SettingsConfigDict(env_prefix='AKI_MEMORY_')` |  |


---

#### class `ContextSettings(BaseSettings)`

```
Context management configuration.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `max_context_tokens` | `int` | `128000` | Maximum context window tokens for the primary model |
| `compaction_threshold` | `float` | `0.75` | Fraction of message budget that triggers compaction (0.0-1.0) |
| `reserve_tokens` | `int` | `4000` | Token buffer reserved for model output |
| `max_compaction_failures` | `int` | `3` | Consecutive compaction failures before circuit breaker trips |
| `model_config` | `` | `SettingsConfigDict(env_prefix='AKI_CONTEXT_')` |  |


---

#### class `ResilienceSettings(BaseSettings)`

```
Resilience / error recovery configuration.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `failover_models` | `list[str]` | `` | Ordered list of fallback models for provider failover |
| `backoff_base_delay` | `float` | `1.0` | Base delay in seconds for exponential backoff |
| `backoff_max_delay` | `float` | `60.0` | Maximum delay in seconds for exponential backoff |
| `backoff_max_retries` | `int` | `5` | Maximum number of retries for rate-limited requests |
| `max_consecutive_errors` | `int` | `3` | Consecutive errors before circuit breaker aborts the agent loop |
| `model_config` | `` | `SettingsConfigDict(env_prefix='AKI_RESILIENCE_')` |  |


---

#### class `HookSettings(BaseSettings)`

```
Hook + permission system configuration.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled` | `bool` | `True` | Enable the hook/event system (disable for minimal overhead) |
| `default_permission_mode` | `str` | `'default'` | Default permission mode for agents without an explicit setting (bypass|default|auto|strict|plan) |
| `model_config` | `` | `SettingsConfigDict(env_prefix='AKI_HOOKS_')` |  |


---

#### class `GatewaySettings(BaseSettings)`

```
Gateway configuration for multi-platform messaging.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `discord_token` | `Optional[str]` | `None` | Discord bot token |
| `discord_channel_ids` | `Optional[str]` | `None` | Comma-separated allowed Discord channel IDs (empty = all) |
| `session_dir` | `str` | `'.aki/sessions'` | Directory for JSONL session persistence |
| `compaction_max_tokens` | `int` | `8000` | Max estimated context tokens before compaction triggers |
| `compaction_threshold` | `float` | `0.8` | Fraction of max_tokens that triggers compaction (0.0-1.0) |
| `default_llm` | `str` | `'openai:gpt-4o'` | Default LLM for gateway sessions |
| `model_config` | `` | `SettingsConfigDict(env_prefix='AKI_GATEWAY_', env_file='.env', env_file_enco` |  |


---

#### class `Settings(BaseSettings)`

```
Main application settings.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `openai_api_key` | `Optional[str]` | `None` | OpenAI API Key |
| `anthropic_api_key` | `Optional[str]` | `None` | Anthropic API Key |
| `google_api_key` | `Optional[str]` | `None` | Google API Key |
| `dashscope_api_key` | `Optional[str]` | `None` | DashScope API Key |
| `pyannote_api_key` | `Optional[str]` | `None` | Pyannote API Key |
| `tavily_api_key` | `Optional[str]` | `None` | Tavily API Key |
| `default_llm` | `str` | `'openai:gpt-4o'` | Default LLM model |
| `default_vlm` | `str` | `'openai:gpt-4o'` | Default VLM model |
| `default_audio` | `str` | `'qwen:qwen3-asr-flash'` | Default audio model |
| `default_embedding` | `str` | `'openai:text-embedding-3-small'` | Default embedding model |
| `openai_base_url` | `Optional[str]` | `None` | Custom OpenAI-compatible endpoint |
| `agent` | `AgentSettings` | `` |  |
| `memory` | `MemorySettings` | `` |  |
| `context` | `ContextSettings` | `` |  |
| `resilience` | `ResilienceSettings` | `` |  |
| `hooks` | `HookSettings` | `` |  |
| `gateway` | `GatewaySettings` | `` |  |
| `model_config` | `` | `SettingsConfigDict(env_prefix='AKI_', env_file='.env', env_file_encoding='ut` |  |

**方法：**

##### `def fallback_openai_key(cls, v: Optional[str]) -> Optional[str]` <small>(L203)</small>

Fallback to OPENAI_API_KEY if AKI_OPENAI_API_KEY not set.

##### `def fallback_anthropic_key(cls, v: Optional[str]) -> Optional[str]` <small>(L211)</small>

Fallback to ANTHROPIC_API_KEY if AKI_ANTHROPIC_API_KEY not set.

##### `def fallback_google_key(cls, v: Optional[str]) -> Optional[str]` <small>(L219)</small>

Fallback to GOOGLE_API_KEY if AKI_GOOGLE_API_KEY not set.

##### `def fallback_tavily_key(cls, v: Optional[str]) -> Optional[str]` <small>(L227)</small>

Fallback to TAVILY_API_KEY if AKI_TAVILY_API_KEY not set.

##### `def fallback_dashscope_key(cls, v: Optional[str]) -> Optional[str]` <small>(L235)</small>

Fallback to DASHSCOPE_API_KEY if AKI_DASHSCOPE_API_KEY not set.

##### `def fallback_pyannote_key(cls, v: Optional[str]) -> Optional[str]` <small>(L243)</small>

Fallback to PYANNOTE_API_KEY if AKI_PYANNOTE_API_KEY not set.


---

#### `def get_settings() -> Settings` <small>(L254)</small>

Get the global settings instance (singleton).


---

#### `def reset_settings() -> None` <small>(L262)</small>

Reset the global settings instance (useful for testing).



---

