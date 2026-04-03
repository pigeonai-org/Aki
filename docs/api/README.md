# Aki API 文档索引

> 自动生成自源码 AST 分析，包含所有模块、类、方法的完整签名和文档。

## 核心模块

| 文档 | 模块 | 说明 | 文件数 |
|------|------|------|--------|
| [agent.md](agent.md) | `aki.agent` | Agent 核心系统 — 执行循环、编排器、角色、身份、通信 | 11 |
| [tools.md](tools.md) | `aki.tools` | 工具系统 — 基类、并行引擎、26 个内置工具 | 26 |
| [context.md](context.md) | `aki.context` | Context 管理 — Token 预算、压缩策略链 | 4 |
| [hooks.md](hooks.md) | `aki.hooks` | Hook + 权限 — 事件分发、权限规则 | 4 |
| [resilience.md](resilience.md) | `aki.resilience` | 弹性恢复 — 退避、Failover、错误分类 | 3 |

## 基础设施

| 文档 | 模块 | 说明 | 文件数 |
|------|------|------|--------|
| [memory.md](memory.md) | `aki.memory` | 记忆系统 — 短期/长期存储、共享状态 | 8 |
| [models.md](models.md) | `aki.models` | 模型适配层 — LLM/VLM/Audio 接口、4 个 Provider | 11 |
| [config.md](config.md) | `aki.config` | 全局配置 — Settings + 环境变量 | 1 |

## 接口层

| 文档 | 模块 | 说明 | 文件数 |
|------|------|------|--------|
| [api.md](api.md) | `aki.api` | REST API — FastAPI 路由、会话管理 | 4 |
| [gateway.md](gateway.md) | `aki.gateway` | 多平台网关 — 消息队列、Discord 适配 | 7 |
| [mcp.md](mcp.md) | `aki.mcp` | MCP 协议 — 客户端/服务端双向适配 | 6 |
| [cli.md](cli.md) | `aki.cli` | 命令行 — Typer CLI | 1 |

## 其他

| 文档 | 模块 | 说明 | 文件数 |
|------|------|------|--------|
| [skills.md](skills.md) | `aki.skills` | 技能注册表 | 1 |
| [runtime.md](runtime.md) | `aki.runtime` | 依赖注入 | 1 |

## 架构文档

- [architecture.md](../architecture.md) — 系统架构总览、模块关系图、核心数据流
- [agent_role_policy.md](../agent_role_policy.md) — Agent 角色策略
- [memory_architecture.md](../memory_architecture.md) — 记忆架构设计

## 文档约定

- 每个文件按 `## aki.module.submodule` 组织
- 每个类标注 `#### class ClassName(Base)`
- 每个方法标注 `##### def method(args) -> ReturnType` 及行号 `(Lxx)`
- 属性表包含类型、默认值、说明
- 完整 docstring 以代码块形式展示
