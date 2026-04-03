# Memory Architecture Guide

## Overview

Aki now uses a two-layer memory system:

1. **Short-term memory**: task-scoped working context (including multimodal artifacts).
2. **Long-term memory**: persistent semantic memory for:
   - `user_instruction`
   - `domain_knowledge`
   - `web_knowledge`

Long-term memory remains **separate** from the `knowledge` module index.

## Core Data Model

`MemoryItem` (`aki/memory/base.py`) now includes:

- `scope`: `short_term` | `long_term`
- `category`: canonical category enum
- `namespace`: logical partition key (default `default`)
- `expires_at`: optional TTL expiry
- `source_uri`: optional source reference
- `fingerprint`: optional dedupe/upsert key

Legacy `type` is preserved for backward compatibility.

## Runtime Wiring

Memory is constructed from settings via:

- `aki/runtime/dependencies.py::build_memory_manager`

Used by:

- CLI task runs (`aki/cli/main.py`)
- deterministic subtitle pipeline (`aki/cli/main.py`)
- MCP server bootstrap (`aki/mcp/server/server.py`)
- MCP adapter fallback orchestrator (`aki/mcp/server/adapter.py`)

## Storage Backends

### Short-term store

- Implementation: `aki/memory/stores/short_term.py`
- In-memory
- Task-scoped indexing
- Per-task and global capacity limits

### Long-term store

- Default backend: vector store (`aki/memory/stores/vector_long_term.py`)
- Engine: ChromaDB + embedding service
- Supports semantic query + metadata filters + TTL prune
- Dedupe/upsert via `fingerprint + namespace + category`

Legacy JSON backend is still available:

- `aki/memory/stores/long_term.py`

## Retrieval Flow

`MemoryManager.recall_context(...)` returns fused context:

- `short_term`: task-local context
- `long_term`: semantic long-term hits
- `combined`: concatenated list for convenience

Agents use this via:

- `BaseAgent.get_memory_observation(...)`

## Ingestion Flow

### Agent loop events

`BaseAgent.run()` now records ReAct loop events into short-term memory:

- `observation`
- `think`
- `action`
- `result`
- `reflect`

### Tool results

`BaseAgent._remember_tool_result(...)` writes tool outcomes into short-term memory.

### Web knowledge auto-ingest

Successful outputs from:

- `web_search`
- `web_read_page`

are transformed into long-term `web_knowledge` entries.

## Retention Policy

Typed TTL defaults:

- `web_knowledge`: expires after `AKI_MEMORY_WEB_TTL_DAYS` (default 30)
- `domain_knowledge`: no expiry by default
- `user_instruction`: no expiry by default

TTL cleanup:

- `MemoryManager.prune_long_term(...)`

## Configuration

All memory settings use `AKI_MEMORY_` prefix.

Key variables:

- `AKI_MEMORY_WINDOW_SIZE`
- `AKI_MEMORY_SHORT_TERM_MAX_ITEMS_PER_TASK`
- `AKI_MEMORY_SHORT_TERM_OBSERVE_LIMIT`
- `AKI_MEMORY_LONG_TERM_ENABLED`
- `AKI_MEMORY_LONG_TERM_BACKEND` (`chroma` | `json`)
- `AKI_MEMORY_LONG_TERM_PERSIST_DIR`
- `AKI_MEMORY_LONG_TERM_COLLECTION`
- `AKI_MEMORY_LONG_TERM_TOP_K`
- `AKI_MEMORY_LONG_TERM_MIN_SCORE`
- `AKI_MEMORY_DEFAULT_NAMESPACE`
- `AKI_MEMORY_WEB_TTL_DAYS`
- `AKI_MEMORY_DOMAIN_TTL_DAYS`
- `AKI_MEMORY_USER_INSTRUCTION_TTL_DAYS`

## Programmatic APIs

Primary APIs (`aki/memory/manager.py`):

- `remember_short_term(...)`
- `remember_long_term(...)`
- `upsert_user_instruction(...)`
- `recall_short_term(...)`
- `recall_long_term(...)`
- `recall_context(...)`
- `prune_long_term(...)`

Backward-compatible aliases still available:

- `remember(...)`
- `recall(...)`
- `consolidate(...)`

## CLI Management Commands

The CLI now includes explicit long-term memory management:

```bash
# Show memory stats
uv run aki memory stats

# List long-term memory
uv run aki memory list --limit 20
uv run aki memory list --query "subtitle style" --categories web_knowledge

# Upsert user instruction
uv run aki memory upsert-instruction style "Use concise imperative subtitle edits."

# Prune expired long-term records
uv run aki memory prune

# Migrate legacy JSON memory file into long-term store
uv run aki memory migrate-legacy-json ./data/memory/memories.json
uv run aki memory migrate-legacy-json ./data/memory/memories.json --dry-run
```

## Testing

Coverage for the upgraded behavior is in:

- `tests/test_memory_management.py`

Scenarios include:

- task isolation in short-term memory
- long-term user-instruction upsert behavior
- web TTL filtering and pruning
- fused short/long context recall
- automatic web tool ingestion into long-term memory
