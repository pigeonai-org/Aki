# `aki.tools` API 文档

> 工具系统 — 包括工具基类、并行执行引擎、所有内置工具（音频/视频/文件/字幕/翻译/搜索等）

---

## `aki.tools.base`

**文件路径：** `aki/tools/base.py`

Tool Base Classes

Tools are pure executors - they perform specific tasks without thinking or decision-making.
This is fundamentally different from Agents, which have ReAct loops.

Tool characteristics:
1. Deterministic: Same input produces same output
2. Stateless: No state preserved between calls
3. Single responsibility: Each tool does one thing
4. Cannot spawn agents or call other tools
---

#### class `ToolParameter(BaseModel)`

```
Tool parameter definition.

Used to generate schema for MCP and OpenAI function calling.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `str` | `` | Parameter name |
| `type` | `str` | `` | Parameter type (string, integer, boolean, array, object) |
| `description` | `str` | `` | Parameter description |
| `required` | `bool` | `True` | Whether the parameter is required |
| `default` | `Any` | `None` | Default value |
| `enum` | `Optional[list[Any]]` | `None` | Allowed values |


---

#### class `ToolResult(BaseModel)`

```
Unified tool execution result.

All tool executions return this standardized result format.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `success` | `bool` | `` | Whether the execution succeeded |
| `data` | `Any` | `None` | Result data |
| `error` | `Optional[str]` | `None` | Error message if failed |
| `metadata` | `dict[str, Any]` | `` | Additional metadata (execution time, resource usage, etc.) |

**方法：**

##### `def ok(cls, data: Any, **metadata: Any) -> 'ToolResult'` <small>(L54)</small>

Create a successful result.

##### `def fail(cls, error: str, **metadata: Any) -> 'ToolResult'` <small>(L59)</small>

Create a failed result.


---

#### class `BaseTool(ABC)`

```
Base class for all tools.

Tools are pure executors with NO thinking capability.
They cannot:
- Access memory
- Access knowledge base
- Call other tools
- Spawn agents
- Make decisions

Subclasses must implement:
- execute(): The main execution logic
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `str` | `''` |  |
| `description` | `str` | `''` |  |
| `parameters` | `list[ToolParameter]` | `[]` |  |
| `concurrency_safe` | `bool` | `False` |  |
| `max_result_size` | `int` | `50000` |  |

**方法：**

##### `def __init__(self) -> None` <small>(L89)</small>

Initialize the tool.

##### `async def execute(self, **kwargs: Any) -> ToolResult` <small>(L97)</small>

Execute the tool.

Subclasses must implement this method.

IMPORTANT:
- Do NOT make decisions here
- Do NOT call other tools
- Only perform the single task

Args:
    **kwargs: Tool-specific parameters

Returns:
    ToolResult with execution outcome

##### `async def execute_streaming(self, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]` <small>(L116)</small>

Streaming execution — yields progress events, then a final result.

Default implementation delegates to execute() and yields a single result.
Override for tools that can report incremental progress (e.g. transcription).

##### `def validate_params(self, **kwargs: Any) -> tuple[bool, Optional[str]]` <small>(L126)</small>

Validate input parameters.

Args:
    **kwargs: Parameters to validate

Returns:
    Tuple of (is_valid, error_message)

##### `async def __call__(self, **kwargs: Any) -> ToolResult` <small>(L150)</small>

Execute the tool with validation.

This is the main entry point for tool execution.

##### `def to_mcp_schema(self) -> dict[str, Any]` <small>(L172)</small>

Convert to MCP tool schema format.

Returns:
    MCP-compatible tool definition

##### `def to_openai_schema(self) -> dict[str, Any]` <small>(L201)</small>

Convert to OpenAI function calling schema format.

Returns:
    OpenAI-compatible function definition

##### `def __repr__(self) -> str` <small>(L231)</small>

String representation.



---

## `aki.tools.delegate_to_worker`

**文件路径：** `aki/tools/delegate_to_worker.py`

Tool for Orchestrator to delegate tasks to specialized worker agents.
---

#### class `DelegateToWorkerTool(BaseTool)`

```
Tool to spawn and run a UniversalAgent with a specialized Role.

This fulfills the pattern where the Orchestrator does not process media
or do direct translations, but hands that off to a targeted sub-agent.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `str` | `'delegate_to_worker'` |  |
| `description` | `str` | `'Delegate a specialized task to a worker agent with a design` |  |
| `parameters` | `list[ToolParameter]` | `[ToolParameter(name='worker_role', type='string', descriptio` | The exact name of the worker role (e.g.,  |

**方法：**

##### `def __init__(self, context: Any = None, llm: Any = None, all_tools: list[BaseTool] | None = None, agent_registry: Any = None) -> None` <small>(L103)</small>

Since this tool creates a new Agent, it needs access to the dependencies.
These should be injected when the tool is initialized by the core system.

##### `async def execute(self, **kwargs: Any) -> ToolResult` <small>(L542)</small>

Execute the delegation.



---

## `aki.tools.executor`

**文件路径：** `aki/tools/executor.py`

Tool Executor

Parallel execution engine for tool calls.
Partitions tool calls by concurrency safety and executes safe tools in parallel.
---

#### class `ToolProgress(BaseModel)`

```
Progress event yielded during streaming tool execution.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `tool_name` | `str` | `''` |  |
| `tool_call_id` | `str` | `''` |  |
| `event` | `str` | `'progress'` |  |
| `message` | `str` | `''` |  |
| `percentage` | `Optional[float]` | `None` |  |
| `data` | `Any` | `None` |  |


---

#### class `ToolCallRequest(BaseModel)`

```
A single tool call to execute.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `call_id` | `str` | `` | Unique ID for this call |
| `tool_name` | `str` | `` | Name of the tool to invoke |
| `params` | `dict[str, Any]` | `` | Tool parameters |


---

#### class `ToolCallResult(BaseModel)`

```
Result of a single tool call execution.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `call_id` | `str` | `` |  |
| `tool_name` | `str` | `` |  |
| `result` | `ToolResult` | `` |  |
| `duration_ms` | `float` | `0.0` |  |


---

#### class `ToolExecutor`

```
Executes tool calls with concurrency partitioning.

Tools with ``concurrency_safe=True`` run in parallel via asyncio.gather().
Unsafe tools run sequentially. Mixed batches are split: safe tools first
(parallel), then unsafe tools (sequential).

Usage::

    executor = ToolExecutor()
    results = await executor.execute_batch(calls, tools)
```

**方法：**

##### `def __init__(self, result_store: Optional[Any] = None, hook_engine: Optional[Any] = None, max_parallel: int = 10) -> None` <small>(L62)</small>

##### `async def execute_batch(self, calls: list[ToolCallRequest], tools: list[BaseTool]) -> list[ToolCallResult]` <small>(L135)</small>

Execute a batch of tool calls with concurrency optimization.

Safe tools run in parallel, unsafe tools run sequentially.
Results are returned in the same order as the input calls.

##### `async def execute_batch_streaming(self, calls: list[ToolCallRequest], tools: list[BaseTool]) -> AsyncGenerator[ToolProgress, None]` <small>(L179)</small>

Execute tools and yield progress events.

Each tool completion yields a ToolProgress with event="complete".



---

## `aki.tools.read_skill`

**文件路径：** `aki/tools/read_skill.py`

Tool for Orchestrator to read full skill files dynamically.
---

#### class `ReadSkillTool(BaseTool)`

```
Tool to fetch the full markdown body of a skill.

This fulfills the Progress Disclosure mechanism where the Orchestrator
only sees metadata initially, and loads the full instructions when needed.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `str` | `'read_skill'` |  |
| `description` | `str` | `'Read the full markdown instructions for a specific skill wo` |  |
| `parameters` | `list[ToolParameter]` | `[ToolParameter(name='skill_name', type='string', description` | The exact name of the skill to read (e.g.,  |
| `concurrency_safe` | `` | `True` |  |

**方法：**

##### `async def execute(self, **kwargs: Any) -> ToolResult` <small>(L34)</small>

Execute the skill read.



---

## `aki.tools.registry`

**文件路径：** `aki/tools/registry.py`

Tool Registry

Manages tool registration and lookup.
---

#### class `ToolRegistry`

```
Tool Registry for managing available tools.

Provides registration, lookup, and schema generation.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|

**方法：**

##### `def register(cls, tool_class: Optional[Type[BaseTool]] = None)` <small>(L23)</small>

Decorator to register a tool class.

Usage:
    @ToolRegistry.register
    class MyTool(BaseTool):
        name = "my_tool"
        ...

##### `def get_class(cls, name: str) -> Type[BaseTool]` <small>(L47)</small>

Get a tool class by name.

Args:
    name: Tool name

Returns:
    Tool class

Raises:
    ValueError: If tool is not registered

##### `def get(cls, name: str, **init_kwargs) -> BaseTool` <small>(L66)</small>

Get a tool instance by name.

If kwargs are provided, creates a new instance.
Otherwise, returns a cached singleton.

Args:
    name: Tool name
    **init_kwargs: Arguments for tool initialization

Returns:
    Tool instance

##### `def list_tools(cls) -> list[str]` <small>(L92)</small>

List all registered tool names.

##### `def get_all_schemas(cls, format: str = 'openai') -> list[dict]` <small>(L97)</small>

Get schemas for all registered tools.

Args:
    format: Schema format ('openai' or 'mcp')

Returns:
    List of tool schemas

##### `def is_registered(cls, name: str) -> bool` <small>(L117)</small>

Check if a tool is registered.

##### `def clear(cls) -> None` <small>(L122)</small>

Clear all registrations and instances (useful for testing).



---

## `aki.tools.result_store`

**文件路径：** `aki/tools/result_store.py`

Large Result Store

Stores tool results that exceed a size threshold to disk.
Returns a file path + preview to keep the LLM context window small.
---

#### class `LargeResultStore`

```
Stores tool results exceeding a threshold to disk.

When a ToolResult's data serializes to more than ``threshold_chars``,
the full result is written to disk and replaced with a truncated preview
plus the file path.

Usage::

    store = LargeResultStore(base_dir=".aki/tool_results")
    result = await tool(**params)
    result = await store.store_if_large(result, tool_name="web_search")
```

**方法：**

##### `def __init__(self, base_dir: str = '.aki/tool_results', threshold_chars: int = 50000, preview_chars: int = 2000) -> None` <small>(L34)</small>

##### `async def store_if_large(self, result: ToolResult, tool_name: str) -> ToolResult` <small>(L44)</small>

Check result size and store to disk if it exceeds the threshold.

Args:
    result: The tool result to potentially store.
    tool_name: Name of the tool (used in filename).

Returns:
    Original result if small enough, or a modified result with
    a preview and file path reference.

##### `async def retrieve(self, result_path: str) -> Any` <small>(L104)</small>

Retrieve a previously stored result from disk.

Args:
    result_path: Path to the stored result file.

Returns:
    Deserialized result data.

##### `def cleanup(self, max_age_seconds: int = 86400) -> int` <small>(L117)</small>

Remove stored results older than max_age.

Returns:
    Number of files removed.



---

## `aki.tools.skills_search`

**文件路径：** `aki/tools/skills_search.py`

Tool for discovering and ranking available skills.
---

#### class `SkillsSearchTool(BaseTool)`

```
List skills and return query-ranked skill matches.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'skills_search'` |  |
| `description` | `` | `'Search available skills and return ranked matches for a task query.'` |  |
| `parameters` | `` | `[ToolParameter(name='query', type='string', description='Optional natural-langua` |  |
| `concurrency_safe` | `` | `True` |  |

**方法：**

##### `async def execute(self, query: str = '', limit: int = 5, **kwargs: Any) -> ToolResult` <small>(L90)</small>

Return available skills and optional ranked matches for the query.



---

## `aki.tools.agent.read_shared`

**文件路径：** `aki/tools/agent/read_shared.py`

Tool: read_shared_state

Allows an agent to read from the task's SharedTaskMemory.
---

#### class `ReadSharedStateTool(BaseTool)`

```
Read a key from the task's shared memory.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `str` | `'read_shared_state'` |  |
| `description` | `str` | `"Read a value from the shared task memory. Use key='*' to li` |  |
| `parameters` | `list[ToolParameter]` | `[ToolParameter(name='key', type='string', description="The k` | The key to read, or  |
| `concurrency_safe` | `bool` | `True` |  |

**方法：**

##### `def __init__(self, shared_memory: Any = None, task_id: str = '') -> None` <small>(L32)</small>

##### `async def execute(self, **kwargs: Any) -> ToolResult` <small>(L37)</small>



---

## `aki.tools.agent.send_message`

**文件路径：** `aki/tools/agent/send_message.py`

Tool: send_agent_message

Allows an agent to send a message to another agent via the AgentBus.
---

#### class `SendAgentMessageTool(BaseTool)`

```
Send a message to another agent on the bus.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `str` | `'send_agent_message'` |  |
| `description` | `str` | `"Send a message to another agent by address (e.g. 'task:Loca` |  |
| `parameters` | `list[ToolParameter]` | `[ToolParameter(name='recipient', type='string', description=` | Recipient address (agent_id or pattern like  |

**方法：**

##### `def __init__(self, bus: Any = None, agent_id: str = '') -> None` <small>(L38)</small>

##### `async def execute(self, **kwargs: Any) -> ToolResult` <small>(L43)</small>



---

## `aki.tools.agent.write_shared`

**文件路径：** `aki/tools/agent/write_shared.py`

Tool: write_shared_state

Allows an agent to write to the task's SharedTaskMemory.
---

#### class `WriteSharedStateTool(BaseTool)`

```
Write a key-value pair to the task's shared memory.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `str` | `'write_shared_state'` |  |
| `description` | `str` | `'Write a value to the shared task memory so other agents can` |  |
| `parameters` | `list[ToolParameter]` | `[ToolParameter(name='key', type='string', description='The k` | The key to write. |

**方法：**

##### `def __init__(self, shared_memory: Any = None, task_id: str = '') -> None` <small>(L38)</small>

##### `async def execute(self, **kwargs: Any) -> ToolResult` <small>(L43)</small>



---

## `aki.tools.audio.extract`

**文件路径：** `aki/tools/audio/extract.py`

Audio Extraction Tool

Extracts mono compressed audio from video files via ffmpeg.
---

#### class `AudioExtractTool(BaseTool)`

```
Extract audio from media for downstream ASR tasks.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'audio_extract'` |  |
| `description` | `` | `'Extract compressed mono audio from a media file using ffmpeg'` |  |
| `parameters` | `` | `[ToolParameter(name='video_path', type='string', description='Path to the source` |  |

**方法：**

##### `async def execute(self, video_path: str, output_path: Optional[str] = None, sample_rate: int = 16000, channels: int = 1, bitrate: str = '48k', **kwargs: Any) -> ToolResult` <small>(L39)</small>

Extract audio track from media file to compressed mp3.



---

## `aki.tools.audio.transcribe`

**文件路径：** `aki/tools/audio/transcribe.py`

Transcribe Tool

Speech recognition using configurable ASR providers.
Pure executor - no decision making.
---

#### class `_ChunkSpec`

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `index` | `int` | `` |  |
| `audio_path` | `str` | `` |  |
| `start_seconds` | `float` | `` |  |
| `end_seconds` | `float` | `` |  |


---

#### class `TranscribeTool(BaseTool)`

```
ASR transcription tool.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'transcribe'` |  |
| `description` | `` | `'Transcribe audio to text using the configured ASR model'` |  |
| `parameters` | `` | `[ToolParameter(name='audio_path', type='string', description='Path to the audio ` |  |

**方法：**

##### `def __init__(self, audio_model: Optional[AudioModelInterface] = None, model_config: Optional[ModelConfig] = None)` <small>(L811)</small>

##### `async def execute(self, audio_path: str, language: Optional[str] = None, prompt: Optional[str] = None, provider: Optional[str] = None, model: Optional[str] = None, chunks: Optional[list[dict[str, Any]]] = None, **kwargs: Any) -> ToolResult` <small>(L820)</small>

Execute speech recognition.



---

## `aki.tools.audio.vad`

**文件路径：** `aki/tools/audio/vad.py`

Audio VAD Tool

Pyannote-based VAD/diarization (default) with pydub chunk export for ASR.
---

#### class `AudioVADTool(BaseTool)`

```
Pyannote-based VAD that exports timestamped audio chunks.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'audio_vad'` |  |
| `description` | `` | `'Run pyannote diarization and split media into VAD audio chunks'` |  |
| `parameters` | `` | `[ToolParameter(name='audio_path', type='string', description='Path or URL to sou` |  |

**方法：**

##### `async def execute(self, audio_path: str, output_dir: str | None = None, provider: str = 'pyannote_api', model: str = 'precision-2', api_key: str | None = None, webhook_url: str | None = None, min_segment_seconds: float = 0.6, max_chunk_seconds: float = 24.0, poll_interval_seconds: float = 1.0, timeout_seconds: float = 600.0, sample_rate: int = 16000, channels: int = 1, bitrate: str = '48k', **kwargs: Any) -> ToolResult` <small>(L309)</small>

Run pyannote diarization and export chunked audio from resulting segments.



---

## `aki.tools.io.file`

**文件路径：** `aki/tools/io/file.py`

File I/O Tool

General file reading and writing operations.
Pure executor - no decision making.
---

#### class `FileReadTool(BaseTool)`

```
File reader tool.

Reads content from local files.
Supports text files of various formats.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'file_read'` |  |
| `description` | `` | `'Read content from a local file. Supports text files like .txt, .md, .json, .py,` |  |
| `parameters` | `` | `[ToolParameter(name='file_path', type='string', description='Path to the file to` |  |
| `concurrency_safe` | `` | `True` |  |

**方法：**

##### `async def execute(self, file_path: str, encoding: str = 'utf-8', **kwargs: Any) -> ToolResult` <small>(L37)</small>

Read file content.

Args:
    file_path: Path to the file
    encoding: Text encoding

Returns:
    ToolResult with file content


---

#### class `FileWriteTool(BaseTool)`

```
File writer tool.

Writes content to local files.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'file_write'` |  |
| `description` | `` | `'Write content to a local file. Creates parent directories if needed.'` |  |
| `parameters` | `` | `[ToolParameter(name='file_path', type='string', description='Path to the file to` |  |

**方法：**

##### `async def execute(self, file_path: str, content: str, encoding: str = 'utf-8', append: bool = False, **kwargs: Any) -> ToolResult` <small>(L115)</small>

Write content to file.

Args:
    file_path: Path to the file
    content: Content to write
    encoding: Text encoding
    append: Append mode

Returns:
    ToolResult with status


---

#### class `FileListTool(BaseTool)`

```
Directory listing tool.

Lists files in a directory.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'file_list'` |  |
| `description` | `` | `'List files and directories in a given path'` |  |
| `parameters` | `` | `[ToolParameter(name='directory_path', type='string', description='Path to the di` |  |
| `concurrency_safe` | `` | `True` |  |

**方法：**

##### `async def execute(self, directory_path: str, pattern: str = '*', recursive: bool = False, **kwargs: Any) -> ToolResult` <small>(L177)</small>

List directory contents.

Args:
    directory_path: Path to directory
    pattern: Glob pattern
    recursive: Recursive listing

Returns:
    ToolResult with file list



---

## `aki.tools.io.pdf`

**文件路径：** `aki/tools/io/pdf.py`

PDF Processing Tools

Tools for reading and processing PDF files.
---

#### class `PDFReadTool(BaseTool)`

```
PDF reader tool using PyMuPDF.

Extracts text content and metadata from PDF files.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'pdf_read'` |  |
| `description` | `` | `'Read and extract text content from a PDF file. Returns text per page.'` |  |
| `parameters` | `` | `[ToolParameter(name='file_path', type='string', description='Path to the PDF fil` |  |
| `concurrency_safe` | `` | `True` |  |

**方法：**

##### `async def execute(self, file_path: str, start_page: int = 1, end_page: int | None = None, **kwargs: Any) -> ToolResult` <small>(L49)</small>

Read PDF content.

Args:
    file_path: Path to PDF file
    start_page: Start page (1-indexed)
    end_page: End page (1-indexed)

Returns:
    ToolResult with extracted text



---

## `aki.tools.io.srt`

**文件路径：** `aki/tools/io/srt.py`

SRT Subtitle Tool

Read and write SRT subtitle files.
Pure executor - no decision making.
---

#### class `SubtitleEntry(BaseModel)`

```
A single subtitle entry.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `index` | `int` | `` | Subtitle index |
| `start_time` | `str` | `` | Start time (HH:MM:SS,mmm) |
| `end_time` | `str` | `` | End time (HH:MM:SS,mmm) |
| `text` | `str` | `` | Subtitle text (source or target) |
| `src_text` | `Optional[str]` | `` | Source text |
| `translation` | `Optional[str]` | `` | Translated text |


---

#### class `SRTReadTool(BaseTool)`

```
SRT file reader tool.

Reads and parses SRT subtitle files.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'srt_read'` |  |
| `description` | `` | `'Read and parse SRT subtitle file'` |  |
| `parameters` | `` | `[ToolParameter(name='file_path', type='string', description='Path to the SRT fil` |  |
| `concurrency_safe` | `` | `True` |  |

**方法：**

##### `async def execute(self, file_path: str, **kwargs: Any) -> ToolResult` <small>(L47)</small>

Read SRT file.

Args:
    file_path: Path to SRT file

Returns:
    ToolResult with parsed subtitles


---

#### class `SRTWriteTool(BaseTool)`

```
SRT file writer tool.

Writes subtitles to SRT format.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'srt_write'` |  |
| `description` | `` | `'Write subtitles to SRT file'` |  |
| `parameters` | `` | `[ToolParameter(name='file_path', type='string', description='Output file path'),` |  |

**方法：**

##### `async def execute(self, file_path: str, subtitles: list[dict[str, Any]], prefer_translation: bool = False, **kwargs: Any) -> ToolResult` <small>(L135)</small>

Write SRT file.

Args:
    file_path: Output path
    subtitles: List of subtitle dicts
    prefer_translation: Write translation field if available

Returns:
    ToolResult with status



---

## `aki.tools.io.web`

**文件路径：** `aki/tools/io/web.py`

Web Access Tools

Tools for interacting with the web:
- TavilySearchTool: Search the web using Tavily API
- WebPageReadTool: Read and parse content from web pages
---

#### class `TavilySearchTool(BaseTool)`

```
Web search tool using Tavily API.

Designed for LLM agents to perform robust web searches.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'web_search'` |  |
| `description` | `` | `'Search the web for information using Tavily API. Returns summaries and URLs.'` |  |
| `parameters` | `` | `[ToolParameter(name='query', type='string', description='The search query')]` |  |
| `concurrency_safe` | `` | `True` |  |

**方法：**

##### `def __init__(self) -> None` <small>(L46)</small>

##### `async def execute(self, query: str, search_depth: str = 'basic', max_results: int = 5, include_domains: Optional[list[str]] = None, exclude_domains: Optional[list[str]] = None, **kwargs: Any) -> ToolResult` <small>(L50)</small>

Execute web search.

Args:
    query: Search query
    search_depth: 'basic' or 'advanced'
    max_results: Number of results
    include_domains: Domains to include
    exclude_domains: Domains to exclude

Returns:
    ToolResult with search results


---

#### class `WebPageReadTool(BaseTool)`

```
Web page reader tool.

Fetches and parses content from a URL using trafilatura for text extraction.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'web_read_page'` |  |
| `description` | `` | `'Read and extract main text content from a web page URL.'` |  |
| `parameters` | `` | `[ToolParameter(name='url', type='string', description='URL of the web page to re` |  |
| `concurrency_safe` | `` | `True` |  |

**方法：**

##### `async def execute(self, url: str, include_links: bool = False, **kwargs: Any) -> ToolResult` <small>(L121)</small>

Fetch and parse web page.

Args:
    url: Page URL
    include_links: Whether to include links in text

Returns:
    ToolResult with page content



---

## `aki.tools.memory.index`

**文件路径：** `aki/tools/memory/index.py`

Helper for injecting the memory index into the agent system prompt.

This module is NOT a tool — it provides a synchronous function that scans the
memory directory and returns a lightweight index (name + description) suitable
for embedding in the system prompt.
---

#### `def get_memory_index(limit: int = 20) -> list[dict[str, str]]` <small>(L30)</small>

Return a compact index of all memory entries.

Each entry contains ``name``, ``description``, and ``updated_at``.
Results are sorted by ``updated_at`` descending and capped at *limit*.



---

## `aki.tools.memory.memory`

**文件路径：** `aki/tools/memory/memory.py`

Long-term memory tools.

Human-readable .md files with YAML frontmatter stored in a configurable
directory.  The agent uses these tools to build and maintain a persistent
knowledge base across sessions.
---

#### class `MemoryListTool(BaseTool)`

```
List all long-term memory entries with their names and descriptions.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'memory_list'` |  |
| `description` | `` | `'List available long-term memory entries. Returns name, description, and last-up` |  |
| `parameters` | `list[ToolParameter]` | `[]` |  |
| `concurrency_safe` | `` | `True` |  |

**方法：**

##### `async def execute(self, **kwargs: Any) -> ToolResult` <small>(L93)</small>


---

#### class `MemoryReadTool(BaseTool)`

```
Read the full content of a specific long-term memory entry.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'memory_read'` |  |
| `description` | `` | `'Read a long-term memory entry by name. Returns the frontmatter metadata and ful` |  |
| `parameters` | `` | `[ToolParameter(name='memory_name', type='string', description='Name of the memor` |  |
| `concurrency_safe` | `` | `True` |  |

**方法：**

##### `async def execute(self, memory_name: str, **kwargs: Any) -> ToolResult` <small>(L140)</small>


---

#### class `MemoryWriteTool(BaseTool)`

```
Create or update a long-term memory entry.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'memory_write'` |  |
| `description` | `` | `'Create or update a long-term memory entry. The entry is stored as a .md file wi` |  |
| `parameters` | `` | `[ToolParameter(name='memory_name', type='string', description="Identifier for th` |  |

**方法：**

##### `async def execute(self, memory_name: str, description: str, body: str, type: str = 'notes', tags: str = '', **kwargs: Any) -> ToolResult` <small>(L207)</small>



---

## `aki.tools.personality.personality`

**文件路径：** `aki/tools/personality/personality.py`

Personality tools.

Manage agent communication style via ``.aki/personality/`` directory.
Personality files are markdown with YAML frontmatter (name, description).
The active personality is stored as ``active.md``.
---

#### class `PersonalityListTool(BaseTool)`

```
List all available personality styles and the currently active one.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'personality_list'` |  |
| `description` | `` | `'List available personality styles from .aki/personality/. Returns name, des` |  |
| `parameters` | `list[ToolParameter]` | `[]` |  |

**方法：**

##### `async def execute(self, **kwargs: Any) -> ToolResult` <small>(L49)</small>


---

#### class `PersonalitySelectTool(BaseTool)`

```
Activate a personality style by copying it to active.md.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'personality_select'` |  |
| `description` | `` | `'Select and activate a personality style. Pass the filename (without .md) of the` |  |
| `parameters` | `list[ToolParameter]` | `[ToolParameter(name='filename', type='string', description='` | The filename (without .md extension) of the personality to activate. Use personality_list to see available options. |

**方法：**

##### `async def execute(self, **kwargs: Any) -> ToolResult` <small>(L111)</small>



---

## `aki.tools.subtitle.editor`

**文件路径：** `aki/tools/subtitle/editor.py`

Subtitle editing tool.
---

#### class `SubtitleEditTool(BaseTool)`

```
Final style and coherence pass for subtitle entries.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'subtitle_edit'` |  |
| `description` | `` | `'Edit subtitles for coherence and style'` |  |
| `parameters` | `` | `[ToolParameter(name='subtitles', type='array', description='List of subtitle ent` |  |

**方法：**

##### `def __init__(self, llm_model: Optional[LLMInterface] = None, model_config: Optional[ModelConfig] = None)` <small>(L36)</small>

##### `async def execute(self, subtitles: list[dict[str, Any]], domain: str = 'general', instructions: Optional[str] = None, context_window: int = 3, suggestions: Optional[list[dict[str, Any]]] = None, **kwargs: Any) -> ToolResult` <small>(L50)</small>

Execute subtitle editing.



---

## `aki.tools.subtitle.proofreader`

**文件路径：** `aki/tools/subtitle/proofreader.py`

Subtitle proofreading tool.
---

#### class `SubtitleProofreadTool(BaseTool)`

```
Review translated subtitle entries and return suggestions only.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'subtitle_proofread'` |  |
| `description` | `` | `'Review translated subtitles and provide non-mutating suggestions'` |  |
| `parameters` | `` | `[ToolParameter(name='subtitles', type='array', description='List of subtitle ent` |  |

**方法：**

##### `def __init__(self, llm_model: Optional[LLMInterface] = None, model_config: Optional[ModelConfig] = None, rag: Optional[Any] = None)` <small>(L48)</small>

##### `async def execute(self, subtitles: list[dict[str, Any]], target_language: str, context: Optional[str] = None, batch_size: int = 5, max_suggestions: int = 50, **kwargs: Any) -> ToolResult` <small>(L64)</small>

Execute subtitle proofreading.



---

## `aki.tools.subtitle.translator`

**文件路径：** `aki/tools/subtitle/translator.py`

Subtitle translation tool.
---

#### class `SubtitleTranslateTool(BaseTool)`

```
Translate SRT entries with optional context and post-split.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'subtitle_translate'` |  |
| `description` | `` | `'Translate subtitles with context and optional long-line splitting'` |  |
| `parameters` | `` | `[ToolParameter(name='subtitles', type='array', description='List of subtitle ent` |  |

**方法：**

##### `def __init__(self, llm_model: Optional[LLMInterface] = None, model_config: Optional[ModelConfig] = None, rag: Optional[Any] = None)` <small>(L47)</small>

##### `async def execute(self, subtitles: list[dict[str, Any]], source_language: str, target_language: str, domain: str = 'general', batch_size: int = 5, split_threshold: int = 80, **kwargs: Any) -> ToolResult` <small>(L132)</small>

Execute subtitle translation.



---

## `aki.tools.text.translate`

**文件路径：** `aki/tools/text/translate.py`

Translation Tool

Translate text using LLM.
Pure executor - no decision making.
---

#### class `TranslateTool(BaseTool)`

```
Text translation tool.

Translates text using LLM-based translation.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'translate_text'` |  |
| `description` | `` | `'Translate text from one language to another using LLM'` |  |
| `parameters` | `` | `[ToolParameter(name='text', type='string', description='Text to translate')]` |  |
| `concurrency_safe` | `` | `True` |  |

**方法：**

##### `def __init__(self, llm_model: Optional[LLMInterface] = None, model_config: Optional[ModelConfig] = None)` <small>(L45)</small>

Initialize the translation tool.

Args:
    llm_model: Pre-configured LLM interface
    model_config: Model configuration (auto-configured with API key if not provided)

##### `async def execute(self, text: str, target_language: str, source_language: str = 'auto', style: str = 'natural', **kwargs: Any) -> ToolResult` <small>(L67)</small>

Execute translation.

Args:
    text: Text to translate
    target_language: Target language
    source_language: Source language
    style: Translation style

Returns:
    ToolResult with translation


---

#### class `ProofreadTool(BaseTool)`

```
Text proofreading tool.

Reviews and corrects translated text.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'proofread_text'` |  |
| `description` | `` | `'Proofread and correct translated text for quality'` |  |
| `parameters` | `` | `[ToolParameter(name='text', type='string', description='Text to proofread'), Too` |  |
| `concurrency_safe` | `` | `True` |  |

**方法：**

##### `def __init__(self, llm_model: Optional[LLMInterface] = None, model_config: Optional[ModelConfig] = None)` <small>(L150)</small>

##### `async def execute(self, text: str, language: str, context: Optional[str] = None, **kwargs: Any) -> ToolResult` <small>(L164)</small>

Execute proofreading.

Args:
    text: Text to proofread
    language: Language of the text
    context: Additional context

Returns:
    ToolResult with corrections



---

## `aki.tools.vision.analyze`

**文件路径：** `aki/tools/vision/analyze.py`

Vision Analysis Tool

Analyze images using vision-language models.
Pure executor - no decision making.
---

#### class `VisionAnalyzeTool(BaseTool)`

```
Vision analysis tool.

Analyzes images using vision-language models (GPT-4V, etc.).
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'vision_analyze'` |  |
| `description` | `` | `'Analyze images using vision-language models'` |  |
| `parameters` | `` | `[ToolParameter(name='images', type='array', description='List of image paths or ` |  |
| `concurrency_safe` | `` | `True` |  |

**方法：**

##### `def __init__(self, vlm_model: Optional[VLMInterface] = None, model_config: Optional[ModelConfig] = None)` <small>(L55)</small>

Initialize the vision analysis tool.

Args:
    vlm_model: Pre-configured VLM interface
    model_config: Model configuration (auto-configured with API key if not provided)

##### `async def execute(self, images: list[Union[str, bytes]], prompt: str, detail: str = 'auto', **kwargs: Any) -> ToolResult` <small>(L87)</small>

Execute image analysis.

Args:
    images: List of image paths or URLs
    prompt: Analysis prompt
    detail: Image detail level

Returns:
    ToolResult with analysis



---

## `aki.tools.vision.video`

**文件路径：** `aki/tools/vision/video.py`

Video Frame Extraction Tool

Extract frames from a video file for vision analysis.
---

#### class `VideoFrameExtractTool(BaseTool)`

```
Extract frames from a video file.

Uses ffmpeg if available on the system PATH.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `` | `'video_extract_frames'` |  |
| `description` | `` | `'Extract frames from a video file for vision analysis'` |  |
| `parameters` | `` | `[ToolParameter(name='video_path', type='string', description='Path to the video ` |  |

**方法：**

##### `async def execute(self, video_path: str, frame_interval_sec: int = 1, max_frames: int = 12, output_dir: Optional[str] = None, image_format: str = 'jpg', **kwargs: Any) -> ToolResult` <small>(L36)</small>

Extract frames from a video file using ffmpeg.



---

