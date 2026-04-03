# `aki.models` API 文档

> 模型适配层 — 统一接口（LLM/VLM/Audio/Embedding）、多 Provider 适配（OpenAI/Anthropic/Google/Qwen）

---

## `aki.models.base`

**文件路径：** `aki/models/base.py`

Model Base Classes

Unified abstraction layer for all model calls.
Supports multiple providers and model types.
---

#### class `ModelType(Enum)`

```
Supported model types.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `LLM` | `` | `'llm'` |  |
| `VLM` | `` | `'vlm'` |  |
| `AUDIO` | `` | `'audio'` |  |
| `EMBEDDING` | `` | `'embedding'` |  |


---

#### class `ModelConfig(BaseModel)`

```
Model configuration.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `provider` | `str` | `` | Provider name (openai, anthropic, google, local) |
| `model_name` | `str` | `` | Model name (gpt-4o, claude-3, gemini-2.0-flash) |
| `api_key` | `Optional[str]` | `None` | API key (optional, uses env if not set) |
| `base_url` | `Optional[str]` | `None` | Custom API endpoint |
| `extra_params` | `dict[str, Any]` | `` | Additional parameters |

**方法：**

##### `def from_string(cls, model_string: str, api_key: Optional[str] = None) -> 'ModelConfig'` <small>(L34)</small>

Create config from string format 'provider:model_name'.

Example: 'openai:gpt-4o' -> ModelConfig(provider='openai', model_name='gpt-4o')


---

#### class `ToolCall(BaseModel)`

```
A single tool call requested by the model.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `id` | `str` | `` | Unique tool call identifier |
| `name` | `str` | `` | Tool name |
| `input` | `dict[str, Any]` | `` | Tool input parameters |


---

#### class `ModelResponse(BaseModel)`

```
Unified model response.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `content` | `Any` | `` | Response content (text string when no tool calls) |
| `usage` | `Optional[dict[str, int]]` | `None` | Token usage statistics |
| `model` | `str` | `` | Model name used |
| `metadata` | `dict[str, Any]` | `` | Additional metadata |
| `tool_calls` | `list[ToolCall]` | `` | Tool calls requested by the model |


---

#### class `BaseModelInterface(ABC)`

```
Abstract base class for all model interfaces.

All model implementations must inherit from this class.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `model_type` | `ModelType` | `` |  |

**方法：**

##### `def __init__(self, config: ModelConfig)` <small>(L73)</small>

Initialize the model interface with configuration.

##### `def provider(self) -> str` <small>(L79)</small>

Get the provider name.

##### `def model_name(self) -> str` <small>(L84)</small>

Get the model name.

##### `async def invoke(self, **kwargs: Any) -> ModelResponse` <small>(L89)</small>

Invoke the model synchronously.

Args:
    **kwargs: Model-specific parameters

Returns:
    ModelResponse with the result

##### `async def stream(self, **kwargs: Any) -> AsyncIterator[str]` <small>(L102)</small>

Stream the model response.

Args:
    **kwargs: Model-specific parameters

Yields:
    String chunks of the response

##### `async def close(self) -> None` <small>(L122)</small>

Close any open connections.



---

## `aki.models.config`

**文件路径：** `aki/models/config.py`

Model Configuration

Centralized model API key and configuration management.
---

#### class `ModelSettings(BaseSettings)`

```
Model API configuration.

Supports environment variables and .env files.
All keys are prefixed with AKI_.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `openai_api_key` | `Optional[str]` | `None` | OpenAI API Key |
| `anthropic_api_key` | `Optional[str]` | `None` | Anthropic API Key |
| `google_api_key` | `Optional[str]` | `None` | Google API Key |
| `dashscope_api_key` | `Optional[str]` | `None` | DashScope API Key |
| `default_llm` | `str` | `'openai:gpt-4o'` | Default LLM model |
| `default_vlm` | `str` | `'openai:gpt-4o'` | Default VLM model |
| `default_audio` | `str` | `'qwen:qwen3-asr-flash'` | Default audio model |
| `default_embedding` | `str` | `'openai:text-embedding-3-small'` | Default embedding model |
| `openai_base_url` | `Optional[str]` | `None` | Custom OpenAI-compatible endpoint |
| `model_config` | `` | `SettingsConfigDict(env_prefix='AKI_', env_file='.env', env_file_encoding='ut` |  |

**方法：**

##### `def get_api_key(self, provider: str) -> Optional[str]` <small>(L73)</small>

Get the API key for a provider.

##### `def fallback_dashscope_key(cls, v: Optional[str]) -> Optional[str]` <small>(L85)</small>

Fallback to DASHSCOPE_API_KEY if AKI_DASHSCOPE_API_KEY not set.

##### `def get_default_config(self, model_type: ModelType) -> ModelConfig` <small>(L91)</small>

Get the default model configuration for a model type.


---

#### `def get_model_settings() -> ModelSettings` <small>(L119)</small>

Get the global model settings instance (singleton).


---

#### `def reset_model_settings() -> None` <small>(L127)</small>

Reset the global model settings instance (useful for testing).



---

## `aki.models.registry`

**文件路径：** `aki/models/registry.py`

Model Registry

Provider registration and factory for model instances.
---

#### class `ModelRegistry`

```
Model Provider Registry.

Manages registration and instantiation of model providers.
Uses decorator pattern for easy registration.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|

**方法：**

##### `def register(cls, provider: str, model_type: ModelType)` <small>(L23)</small>

Decorator to register a provider implementation.

Usage:
    @ModelRegistry.register("openai", ModelType.LLM)
    class OpenAILLM(LLMInterface):
        ...

##### `def get(cls, config: ModelConfig, model_type: ModelType) -> BaseModelInterface` <small>(L42)</small>

Get a model instance for the given configuration and type.

Args:
    config: Model configuration
    model_type: Type of model (LLM, VLM, AUDIO, EMBEDDING)

Returns:
    Instantiated model interface

Raises:
    ValueError: If provider or model type is not registered

##### `def get_from_string(cls, model_string: str, model_type: ModelType, api_key: Optional[str] = None) -> BaseModelInterface` <small>(L74)</small>

Get a model instance from a string format.

Args:
    model_string: Format 'provider:model_name' (e.g., 'openai:gpt-4o')
    model_type: Type of model
    api_key: Optional API key

Returns:
    Instantiated model interface

##### `def list_providers(cls) -> list[str]` <small>(L95)</small>

List all registered providers.

##### `def list_model_types(cls, provider: str) -> list[ModelType]` <small>(L100)</small>

List all model types available for a provider.

##### `def is_registered(cls, provider: str, model_type: ModelType) -> bool` <small>(L107)</small>

Check if a provider/model_type combination is registered.

##### `def clear(cls) -> None` <small>(L112)</small>

Clear all registrations (useful for testing).



---

## `aki.models.providers.anthropic`

**文件路径：** `aki/models/providers/anthropic.py`

Anthropic Provider Implementation

Supports Claude models.
---

#### class `AnthropicLLM(LLMInterface)`

```
Anthropic LLM implementation (Claude).
```

**方法：**

##### `def __init__(self, config: ModelConfig)` <small>(L18)</small>

##### `async def chat(self, messages: list[dict[str, Any]], tools: Optional[list[dict[str, Any]]] = None, temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs: Any) -> ModelResponse` <small>(L37)</small>

Chat completion using Anthropic API.

##### `async def stream(self, **kwargs: Any) -> AsyncIterator[str]` <small>(L110)</small>

Stream chat completion.

##### `async def close(self) -> None` <small>(L141)</small>

Close the client.



---

## `aki.models.providers.google`

**文件路径：** `aki/models/providers/google.py`

Google Provider Implementation

Supports Gemini models for LLM, VLM, and Audio.
---

#### class `GeminiLLM(LLMInterface)`

```
Google Gemini LLM implementation.
```

**方法：**

##### `def __init__(self, config: ModelConfig)` <small>(L19)</small>

##### `async def chat(self, messages: list[dict[str, Any]], tools: Optional[list[dict[str, Any]]] = None, temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs: Any) -> ModelResponse` <small>(L37)</small>

Chat completion using Gemini API.

##### `async def stream(self, **kwargs: Any) -> AsyncIterator[str]` <small>(L81)</small>

Stream is not fully implemented for Gemini.


---

#### class `GeminiAudio(AudioModelInterface)`

```
Google Gemini Audio implementation for speech recognition.
```

**方法：**

##### `def __init__(self, config: ModelConfig)` <small>(L90)</small>

##### `async def transcribe(self, audio: Union[str, bytes], language: Optional[str] = None, prompt: Optional[str] = None, **kwargs: Any) -> ModelResponse` <small>(L108)</small>

Transcribe audio using Gemini API.



---

## `aki.models.providers.openai`

**文件路径：** `aki/models/providers/openai.py`

OpenAI Provider Implementation

Supports GPT-4, GPT-4V, Whisper, and text-embedding models.
---

#### class `OpenAILLM(LLMInterface)`

```
OpenAI LLM implementation (GPT-4, GPT-4o, etc.).
```

**方法：**

##### `def __init__(self, config: ModelConfig)` <small>(L25)</small>

##### `async def chat(self, messages: list[dict[str, Any]], tools: Optional[list[dict[str, Any]]] = None, temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs: Any) -> ModelResponse` <small>(L43)</small>

Chat completion using OpenAI API.

##### `async def stream(self, **kwargs: Any) -> AsyncIterator[str]` <small>(L101)</small>

Stream chat completion.

##### `async def close(self) -> None` <small>(L117)</small>

Close the client.


---

#### class `OpenAIVLM(VLMInterface)`

```
OpenAI VLM implementation (GPT-4V, GPT-4o).
```

**方法：**

##### `def __init__(self, config: ModelConfig)` <small>(L128)</small>

##### `async def analyze(self, images: list[Union[str, bytes]], prompt: str, detail: str = 'auto', max_tokens: Optional[int] = None, **kwargs: Any) -> ModelResponse` <small>(L146)</small>

Analyze images using OpenAI Vision API.

##### `async def close(self) -> None` <small>(L223)</small>

Close the client.


---

#### class `OpenAIAudio(AudioModelInterface)`

```
OpenAI Audio implementation (Whisper).
```

**方法：**

##### `def __init__(self, config: ModelConfig)` <small>(L234)</small>

##### `async def transcribe(self, audio: Union[str, bytes], language: Optional[str] = None, prompt: Optional[str] = None, **kwargs: Any) -> ModelResponse` <small>(L252)</small>

Transcribe audio using OpenAI Whisper API.

##### `async def close(self) -> None` <small>(L299)</small>

Close the client.


---

#### class `OpenAIEmbedding(EmbeddingModelInterface)`

```
OpenAI Embedding implementation (text-embedding-3).
```

**方法：**

##### `def __init__(self, config: ModelConfig)` <small>(L310)</small>

##### `async def embed(self, texts: Union[str, list[str]], **kwargs: Any) -> ModelResponse` <small>(L328)</small>

Generate embeddings using OpenAI API.

##### `async def close(self) -> None` <small>(L358)</small>

Close the client.



---

## `aki.models.providers.qwen`

**文件路径：** `aki/models/providers/qwen.py`

Qwen Provider Implementation

Uses DashScope SDK for Qwen models.
Currently provides Audio ASR support.
---

#### class `QwenAudio(AudioModelInterface)`

```
DashScope Qwen ASR implementation.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `DASHSCOPE_INTL_BASE_URL` | `` | `'https://dashscope-intl.aliyuncs.com/api/v1'` |  |
| `DASHSCOPE_US_BASE_URL` | `` | `'https://dashscope-us.aliyuncs.com/api/v1'` |  |
| `MAX_RETRY_ATTEMPTS` | `` | `3` |  |

**方法：**

##### `def __init__(self, config: ModelConfig)` <small>(L28)</small>

##### `async def transcribe(self, audio: Union[str, bytes], language: Optional[str] = None, prompt: Optional[str] = None, **kwargs: Any) -> ModelResponse` <small>(L44)</small>

Transcribe audio using DashScope MultiModalConversation API.



---

## `aki.models.types.audio`

**文件路径：** `aki/models/types/audio.py`

Audio Model Interface

Interface for Audio/Speech Recognition Models.
---

#### class `AudioModelInterface(BaseModelInterface)`

```
Audio Model Interface for speech recognition.

Supports transcription of audio to text.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `model_type` | `` | `ModelType.AUDIO` |  |

**方法：**

##### `async def transcribe(self, audio: Union[str, bytes], language: Optional[str] = None, prompt: Optional[str] = None, **kwargs: Any) -> ModelResponse` <small>(L23)</small>

Transcribe audio to text.

Args:
    audio: Audio file path or bytes
    language: Source language code (e.g., 'en', 'zh')
    prompt: Optional prompt to guide transcription
    **kwargs: Additional model-specific parameters

Returns:
    ModelResponse with transcription result and segments

##### `async def invoke(self, **kwargs: Any) -> ModelResponse` <small>(L44)</small>

Invoke the model using transcribe interface.

##### `async def stream(self, **kwargs: Any)` <small>(L49)</small>

Stream is not implemented for audio models.



---

## `aki.models.types.embedding`

**文件路径：** `aki/models/types/embedding.py`

Embedding Model Interface

Interface for text embedding models.
---

#### class `EmbeddingModelInterface(BaseModelInterface)`

```
Embedding Model Interface for text vectorization.

Converts text to vector embeddings for semantic search.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `model_type` | `` | `ModelType.EMBEDDING` |  |

**方法：**

##### `async def embed(self, texts: Union[str, list[str]], **kwargs: Any) -> ModelResponse` <small>(L23)</small>

Generate embeddings for text(s).

Args:
    texts: Single text or list of texts to embed
    **kwargs: Additional model-specific parameters

Returns:
    ModelResponse with embeddings (list of float vectors)

##### `async def invoke(self, **kwargs: Any) -> ModelResponse` <small>(L40)</small>

Invoke the model using embed interface.

##### `async def stream(self, **kwargs: Any)` <small>(L45)</small>

Stream is not implemented for embedding models.



---

## `aki.models.types.llm`

**文件路径：** `aki/models/types/llm.py`

LLM Interface

Interface for Large Language Models (text generation).
---

#### class `LLMInterface(BaseModelInterface)`

```
LLM Interface for text generation models.

Supports chat completion with optional tool/function calling.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `model_type` | `` | `ModelType.LLM` |  |

**方法：**

##### `async def chat(self, messages: list[dict[str, Any]], tools: Optional[list[dict[str, Any]]] = None, temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs: Any) -> ModelResponse` <small>(L23)</small>

Chat completion.

Args:
    messages: List of message dicts with 'role' and 'content'
    tools: Optional list of tool definitions for function calling
    temperature: Sampling temperature (0.0-2.0)
    max_tokens: Maximum tokens to generate
    **kwargs: Additional model-specific parameters

Returns:
    ModelResponse with generated text and optional tool calls

##### `async def invoke(self, **kwargs: Any) -> ModelResponse` <small>(L46)</small>

Invoke the model using chat interface.

##### `async def stream(self, **kwargs: Any)` <small>(L51)</small>

Stream is not implemented by default - subclasses should override.



---

## `aki.models.types.vlm`

**文件路径：** `aki/models/types/vlm.py`

VLM Interface

Interface for Vision-Language Models.
---

#### class `VLMInterface(BaseModelInterface)`

```
VLM Interface for vision-language models.

Supports image analysis with text prompts.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `model_type` | `` | `ModelType.VLM` |  |

**方法：**

##### `async def analyze(self, images: list[Union[str, bytes]], prompt: str, detail: str = 'auto', max_tokens: Optional[int] = None, **kwargs: Any) -> ModelResponse` <small>(L23)</small>

Analyze images with a text prompt.

Args:
    images: List of image URLs or base64-encoded bytes
    prompt: Text prompt describing what to analyze
    detail: Image detail level ('low', 'high', 'auto')
    max_tokens: Maximum tokens to generate
    **kwargs: Additional model-specific parameters

Returns:
    ModelResponse with analysis result

##### `async def invoke(self, **kwargs: Any) -> ModelResponse` <small>(L46)</small>

Invoke the model using analyze interface.

##### `async def stream(self, **kwargs: Any)` <small>(L52)</small>

Stream is not implemented by default - subclasses should override.



---

