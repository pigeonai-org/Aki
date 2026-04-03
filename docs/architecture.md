# Aki 架构总览

## 项目定位

Aki 是一个通用 AI Agent 平台，支持多模型、多工具、多 Agent 协作。核心场景包括视频字幕翻译、多语言本地化、文档处理等，同时具备扩展为通用 Agent 框架的能力。

## 模块架构图

```
aki/
├── agent/                  # Agent 核心系统
│   ├── base.py             #   UniversalAgent — 核心 Agent 循环
│   ├── orchestrator.py     #   AgentOrchestrator — 任务调度 + 子系统注入
│   ├── roles.py            #   Role 定义 + 技能前端加载
│   ├── identity.py         #   AgentDefinition + AgentIdentity（持久化身份）
│   ├── agent_registry.py   #   AgentRegistry（Agent 定义发现 + 管理）
│   ├── state.py            #   AgentContext（执行上下文 + 深度控制）
│   ├── logger.py           #   结构化日志（Rich Console）
│   ├── types.py            #   类型定义
│   └── communication/      #   Agent 间通信
│       ├── addressing.py   #     地址解析（project:role:instance）
│       ├── messages.py     #     AgentMessage + AgentEvent
│       └── bus.py          #     AgentBus（消息路由 + 事件广播）
│
├── context/                # Context 管理子系统
│   ├── token_counter.py    #   Token 估算（tiktoken）
│   ├── budget.py           #   TokenBudget（容量追踪）
│   ├── strategies.py       #   压缩策略（StripMedia/SummarizeOld/Truncate）
│   └── manager.py          #   ContextManager（预算分配 + 自动压缩）
│
├── hooks/                  # Hook + 权限系统
│   ├── types.py            #   EventType（12种事件）+ HookEvent + HookResult
│   ├── rules.py            #   PermissionMode + PermissionRule
│   ├── engine.py           #   HookEngine（事件分发 + 优先级）
│   └── permission.py       #   PermissionEngine（规则求值）
│
├── resilience/             # 错误恢复 + Failover
│   ├── backoff.py          #   RateLimitBackoff（指数退避 + 抖动）
│   ├── failover.py         #   ModelFailover / FailoverChain
│   └── recovery.py         #   ErrorRecoveryHandler（错误分类 + 恢复决策）
│
├── tools/                  # 工具系统
│   ├── base.py             #   BaseTool（工具基类 + 并发安全标记）
│   ├── executor.py         #   ToolExecutor（并行执行引擎）
│   ├── result_store.py     #   LargeResultStore（大结果落盘）
│   ├── registry.py         #   ToolRegistry（工具注册表）
│   ├── delegate_to_worker.py # DelegateToWorkerTool（Agent 派遣）
│   ├── read_skill.py       #   ReadSkillTool
│   ├── skills_search.py    #   SkillsSearchTool
│   ├── agent/              #   Agent 间通信工具
│   │   ├── send_message.py #     SendAgentMessageTool
│   │   ├── read_shared.py  #     ReadSharedStateTool
│   │   └── write_shared.py #     WriteSharedStateTool
│   ├── audio/              #   音频处理工具
│   │   ├── extract.py      #     AudioExtractTool
│   │   ├── vad.py          #     AudioVADTool
│   │   └── transcribe.py   #     TranscribeTool
│   ├── io/                 #   文件 I/O 工具
│   │   ├── file.py         #     FileRead/Write/ListTool
│   │   ├── pdf.py          #     PDFReadTool
│   │   ├── srt.py          #     SRTRead/WriteTool
│   │   └── web.py          #     TavilySearchTool + WebPageReadTool
│   ├── memory/             #   记忆管理工具
│   │   ├── index.py        #     get_memory_index()
│   │   └── memory.py       #     MemoryList/Read/WriteTool
│   ├── personality/        #   人格管理工具
│   │   └── personality.py  #     PersonalityList/SelectTool
│   ├── subtitle/           #   字幕处理工具
│   │   ├── editor.py       #     SubtitleEditTool
│   │   ├── proofreader.py  #     SubtitleProofreadTool
│   │   └── translator.py   #     SubtitleTranslateTool
│   ├── text/               #   文本处理工具
│   │   └── translate.py    #     TranslateTool + ProofreadTool
│   └── vision/             #   视觉处理工具
│       ├── analyze.py      #     VisionAnalyzeTool
│       └── video.py        #     VideoFrameExtractTool
│
├── memory/                 # 记忆系统
│   ├── base.py             #   MemoryStore 抽象基类
│   ├── manager.py          #   MemoryManager
│   ├── shared.py           #   SharedTaskMemory（任务内共享状态）
│   ├── migration.py        #   记忆迁移工具
│   ├── types.py            #   记忆类型定义
│   ├── stores/
│   │   ├── short_term.py   #   短期记忆存储
│   │   └── long_term.py    #   长期记忆存储（.md 文件）
│   └── strategies/
│       └── sliding_window.py # 滑动窗口选择策略
│
├── models/                 # 模型适配层
│   ├── base.py             #   模型基类
│   ├── config.py           #   模型配置
│   ├── registry.py         #   ModelRegistry
│   ├── types/
│   │   ├── llm.py          #   LLMInterface + LLMResponse + ToolCall
│   │   ├── vlm.py          #   VLMInterface
│   │   ├── audio.py        #   AudioInterface
│   │   └── embedding.py    #   EmbeddingInterface
│   └── providers/
│       ├── openai.py       #   OpenAI 适配器
│       ├── anthropic.py    #   Anthropic 适配器
│       ├── google.py       #   Google Gemini 适配器
│       └── qwen.py         #   通义千问 / DashScope 适配器
│
├── config/                 # 全局配置
│   └── settings.py         #   Settings（Pydantic Settings，环境变量）
│
├── api/                    # REST API
│   ├── models.py           #   请求/响应模型
│   ├── routes.py           #   FastAPI 路由
│   ├── server.py           #   服务器启动
│   └── session_manager.py  #   会话管理
│
├── gateway/                # 多平台网关
│   ├── gateway.py          #   Gateway 核心
│   ├── compaction.py       #   会话压缩
│   ├── lane_queue.py       #   消息队列
│   ├── persistence.py      #   会话持久化
│   ├── types.py            #   网关类型
│   └── adapters/
│       ├── base.py         #   适配器基类
│       └── discord_adapter.py # Discord 适配器
│
├── mcp/                    # MCP 协议支持
│   ├── config.py           #   MCP 配置
│   ├── client/
│   │   ├── client.py       #   MCP 客户端
│   │   ├── adapter.py      #   MCP→Tool 适配
│   │   └── manager.py      #   多服务器管理
│   └── server/
│       ├── server.py       #   MCP 服务端
│       └── adapter.py      #   Tool→MCP 适配
│
├── cli/                    # 命令行界面
│   └── main.py             #   Typer CLI
│
├── skills/                 # 技能系统
│   └── registry.py         #   技能注册表 + frontmatter 加载
│
└── runtime/                # 运行时
    └── dependencies.py     #   依赖注入
```

## 核心数据流

```
用户消息
    ↓
AgentOrchestrator.run_task(task)
    ↓ 创建 AgentContext, AgentBus, SharedTaskMemory
    ↓ 注入 ContextManager, ErrorRecoveryHandler, HookEngine, PermissionEngine
    ↓
UniversalAgent.run(task)
    ↓
ContextManager.allocate_budget()          ← 计算 token 预算
    ↓
┌─→ HookEngine.fire(SESSION_START)
│       ↓
│   LLM.chat(messages, tools)             ← 自动 failover（ModelFailover）
│       ↓
│   ErrorRecoveryHandler                  ← 异常时：compact / backoff / failover / abort
│       ↓
│   [无 tool_calls? → SESSION_END → 返回结果]
│       ↓
│   HookEngine.fire(PRE_TOOL_USE)
│       ↓
│   PermissionEngine.check_permission()   ← 规则匹配（allow/deny/ask）
│       ↓  [denied → 注入拒绝消息]
│   ToolExecutor.execute_batch(calls)
│       ├── concurrency_safe 工具 → asyncio.gather()
│       └── 非安全工具 → 串行执行
│       ↓
│   LargeResultStore.store_if_large()     ← 大结果落盘
│       ↓
│   HookEngine.fire(POST_TOOL_USE)
│       ↓
│   ContextManager.needs_compaction()?    ← 超阈值则压缩
│       ↓  [是 → CONTEXT_COMPACTION → compact()]
│       ↓
│   TokenBudget.has_capacity()?           ← 预算耗尽则停止
│       ↓
└───────┘ (循环直到完成或预算用尽)
    ↓
SharedTaskMemory.clear_task()             ← 清理任务共享状态
```

## 设计原则

| 原则 | 说明 |
|------|------|
| **渐进式采用** | 所有新子系统都是可选构造参数，未配置时为 no-op |
| **零回归风险** | 每个 Phase 可独立部署，现有功能不受影响 |
| **透明代理** | ModelFailover IS-A LLMInterface，对调用方透明 |
| **安全默认** | concurrency_safe 默认 False，逐个 opt-in |
| **向后兼容** | AgentDefinition 是 Role 的超集，通过桥接方法迁移 |
| **策略可组合** | Context 压缩策略链式执行，StripMedia + SummarizeOld 可组合 |
