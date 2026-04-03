# Aki Architecture Overview

## What This Is

Aki is a general-purpose AI Agent platform. Multi-model, multi-tool, multi-agent coordination. Core use cases include video subtitle translation, multilingual localization, and document processing — but the architecture is designed to extend to anything an agent can do.

## Module Tree

```
aki/
├── agent/                  # Agent core
│   ├── base.py             #   UniversalAgent — the agent loop, native tool calling
│   ├── orchestrator.py     #   AgentOrchestrator — task dispatch + subsystem injection
│   ├── identity.py         #   AgentDefinition + AgentIdentity (persistent identity)
│   ├── agent_registry.py   #   AgentRegistry (agent definition discovery + management)
│   ├── state.py            #   AgentContext (execution context + depth control)
│   ├── task_registry.py    #   TaskRegistry (task tracking)
│   ├── logger.py           #   Structured logging (Rich Console)
│   └── communication/      #   Inter-agent communication
│       ├── addressing.py   #     Address resolution
│       ├── messages.py     #     AgentMessage + AgentEvent
│       └── bus.py          #     AgentBus (message routing + event broadcast)
│
├── personality/            # Personality system — who I am
│   ├── base.md             #   Non-negotiable principles (never overridden)
│   ├── _schema.md          #   Persona definition schema
│   ├── registry.py         #   Persona discovery + loading
│   ├── aki/                #   Aki persona
│   │   ├── aki.md          #     Persona definition
│   │   ├── examples.md     #     Conversation examples (en)
│   │   ├── examples.zh.md  #     Conversation examples (zh)
│   │   ├── story.md        #     Backstory (en)
│   │   └── story.zh.md     #     Backstory (zh)
│   ├── aria/               #   Aria persona (same structure)
│   └── persona_memory/     #   Per-persona persistent memory
│       └── manager.py      #     Persona memory read/write
│
├── memory/                 # Memory system — how I remember
│   ├── base.py             #   MemoryStore base class
│   ├── manager.py          #   MemoryManager — top-level coordination
│   ├── recall.py           #   Session-start recall pipeline
│   ├── review.py           #   Session-end review + promotion to long-term
│   ├── shared.py           #   SharedTaskMemory (within-task shared state)
│   ├── migration.py        #   Legacy memory migration
│   ├── types.py            #   Memory type definitions
│   ├── session/            #   Session memory (Layer 1)
│   │   ├── store.py        #     JSONL session persistence
│   │   └── types.py        #     Session data types
│   ├── dimensions/         #   Long-term memory dimensions (Layer 2)
│   │   ├── base.py         #     Dimension store base class
│   │   ├── user.py         #     User preferences + instructions
│   │   ├── episodic.py     #     Notable events + conversation summaries
│   │   ├── semantic.py     #     Domain knowledge + facts
│   │   ├── persona.py      #     Persona-specific memories
│   │   └── procedural.py   #     Workflow patterns + tool usage
│   ├── stores/
│   │   ├── short_term.py   #   Short-term working memory
│   │   └── long_term.py    #   Long-term memory store
│   └── strategies/
│       └── sliding_window.py # Sliding window selection
│
├── context/                # Context management
│   ├── token_counter.py    #   Token estimation (tiktoken)
│   ├── budget.py           #   TokenBudget (capacity tracking)
│   ├── strategies.py       #   Compression strategies (StripMedia/SummarizeOld/Truncate)
│   └── manager.py          #   ContextManager (budget allocation + auto-compression)
│
├── hooks/                  # Hook + permission system
│   ├── types.py            #   EventType (12 events) + HookEvent + HookResult
│   ├── rules.py            #   PermissionMode + PermissionRule
│   ├── engine.py           #   HookEngine (event dispatch + priority)
│   └── permission.py       #   PermissionEngine (rule evaluation)
│
├── resilience/             # Error recovery + failover
│   ├── backoff.py          #   RateLimitBackoff (exponential + jitter)
│   ├── failover.py         #   ModelFailover / FailoverChain
│   └── recovery.py         #   ErrorRecoveryHandler (classify + recover)
│
├── tools/                  # Tool system
│   ├── base.py             #   BaseTool (tool base class + concurrency_safe flag)
│   ├── executor.py         #   ToolExecutor (parallel execution engine)
│   ├── result_store.py     #   LargeResultStore (large results to disk)
│   ├── registry.py         #   ToolRegistry
│   ├── delegate_to_worker.py # DelegateToWorkerTool (agent delegation)
│   ├── read_skill.py       #   ReadSkillTool
│   ├── skills_search.py    #   SkillsSearchTool
│   ├── agent/              #   Inter-agent communication tools
│   │   ├── check_task.py   #     CheckTaskTool
│   │   ├── send_message.py #     SendAgentMessageTool
│   │   ├── read_shared.py  #     ReadSharedStateTool
│   │   └── write_shared.py #     WriteSharedStateTool
│   ├── audio/              #   Audio processing
│   │   ├── extract.py      #     AudioExtractTool
│   │   ├── vad.py          #     AudioVADTool
│   │   └── transcribe.py   #     TranscribeTool
│   ├── io/                 #   File I/O
│   │   ├── file.py         #     FileRead/Write/ListTool
│   │   ├── pdf.py          #     PDFReadTool
│   │   ├── srt.py          #     SRTRead/WriteTool
│   │   └── web.py          #     TavilySearchTool + WebPageReadTool
│   ├── memory/             #   Memory management tools
│   │   ├── index.py        #     get_memory_index()
│   │   └── memory.py       #     MemoryList/Read/WriteTool
│   ├── personality/        #   Personality tools
│   │   └── personality.py  #     PersonalityList/SelectTool
│   ├── pipeline/           #   Deterministic pipeline tools
│   │   ├── _helpers.py     #     Pipeline utilities
│   │   ├── localize.py     #     LocalizePipelineTool
│   │   ├── media_extract.py #    MediaExtractPipelineTool
│   │   └── qa_edit.py      #     QAEditPipelineTool
│   ├── subtitle/           #   Subtitle processing
│   │   ├── editor.py       #     SubtitleEditTool
│   │   ├── proofreader.py  #     SubtitleProofreadTool
│   │   └── translator.py   #     SubtitleTranslateTool
│   ├── text/               #   Text processing
│   │   └── translate.py    #     TranslateTool + ProofreadTool
│   └── vision/             #   Vision processing
│       ├── analyze.py      #     VisionAnalyzeTool
│       └── video.py        #     VideoFrameExtractTool
│
├── models/                 # Model adapter layer
│   ├── base.py             #   Model base class
│   ├── config.py           #   Model configuration
│   ├── registry.py         #   ModelRegistry
│   ├── types/
│   │   ├── llm.py          #   LLMInterface + LLMResponse + ToolCall
│   │   ├── vlm.py          #   VLMInterface
│   │   ├── audio.py        #   AudioInterface
│   │   └── embedding.py    #   EmbeddingInterface
│   └── providers/
│       ├── openai.py       #   OpenAI adapter
│       ├── anthropic.py    #   Anthropic adapter
│       ├── google.py       #   Google Gemini adapter
│       └── qwen.py         #   Qwen / DashScope adapter
│
├── config/                 # Global configuration
│   └── settings.py         #   Settings (Pydantic Settings, env vars)
│
├── api/                    # REST API
│   ├── models.py           #   Request/response models
│   ├── routes.py           #   FastAPI routes
│   ├── server.py           #   Server startup
│   └── session_manager.py  #   Session management
│
├── gateway/                # Multi-platform gateway
│   ├── gateway.py          #   Gateway core
│   ├── compaction.py       #   Session compaction
│   ├── lane_queue.py       #   Message queue
│   ├── persistence.py      #   Session persistence
│   ├── types.py            #   Gateway types
│   └── adapters/
│       ├── base.py         #   Adapter base class
│       └── discord_adapter.py # Discord adapter
│
├── mcp/                    # MCP protocol support
│   ├── config.py           #   MCP configuration
│   ├── client/
│   │   ├── client.py       #   MCP client
│   │   ├── adapter.py      #   MCP -> Tool adapter
│   │   └── manager.py      #   Multi-server management
│   └── server/
│       ├── server.py       #   MCP server
│       └── adapter.py      #   Tool -> MCP adapter
│
├── cli/                    # Command line interface
│   ├── main.py             #   Typer CLI
│   ├── events.py           #   CLI event handling
│   ├── focus.py            #   Focus mode
│   ├── input.py            #   Input handling
│   └── renderer.py         #   Output rendering
│
├── skills/                 # Skill system
│   └── registry.py         #   Skill registry + frontmatter loading
│
└── runtime/                # Runtime
    └── dependencies.py     #   Dependency injection
```

## Core Data Flow

```
User message
    |
AgentOrchestrator.run_task(task)
    | creates AgentContext, AgentBus, SharedTaskMemory
    | injects ContextManager, ErrorRecoveryHandler, HookEngine, PermissionEngine
    | runs recall pipeline (memory/recall.py) — injects personality + memories
    |
UniversalAgent.run(task)
    |
ContextManager.allocate_budget()          <- compute token budget
    |
+-> HookEngine.fire(SESSION_START)
|       |
|   LLM.chat(messages, tools)             <- native tool calling, auto failover
|       |
|   ErrorRecoveryHandler                  <- on error: compact / backoff / failover / abort
|       |
|   [no tool_calls? -> SESSION_END -> return result]
|       |
|   HookEngine.fire(PRE_TOOL_USE)
|       |
|   PermissionEngine.check_permission()   <- rule matching (allow/deny/ask)
|       |  [denied -> inject denial message]
|   ToolExecutor.execute_batch(calls)
|       |-- concurrency_safe tools -> asyncio.gather()
|       |-- non-safe tools -> sequential
|       |
|   LargeResultStore.store_if_large()     <- large results to disk
|       |
|   HookEngine.fire(POST_TOOL_USE)
|       |
|   ContextManager.needs_compaction()?    <- over threshold -> compress
|       |  [yes -> CONTEXT_COMPACTION -> compact()]
|       |
|   TokenBudget.has_capacity()?           <- budget exhausted -> stop
|       |
+-------+ (loop until done or budget exhausted)
    |
review pass (memory/review.py)            <- promote session memories to long-term
SharedTaskMemory.clear_task()             <- clean up task shared state
```

## Design Principles

| Principle | Description |
|-----------|-------------|
| **Personality-driven** | Identity comes from personality layers, not role enums or agent subclasses |
| **Progressive adoption** | All subsystems are optional constructor params; no-op when unconfigured |
| **Zero regression risk** | Each phase deploys independently; existing functionality unaffected |
| **Transparent proxy** | ModelFailover IS-A LLMInterface, transparent to callers |
| **Safe defaults** | concurrency_safe defaults False; opt-in per tool |
| **Composable strategies** | Context compression chains: StripMedia + SummarizeOld composable |
| **Native tool calling** | The model decides tool use; no ReAct string parsing |
