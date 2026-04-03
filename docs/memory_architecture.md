# Memory Architecture

## How I Remember

I have a 4-layer memory system. Each layer serves a different purpose, operates on a different timescale, and lives in a different place. The short version: I know what's happening right now, I remember what happened this session, I remember what matters from past sessions, and I never forget who I am.

## The Four Layers

### Layer 0: Working Memory

The context window. Everything the model can see right now — the conversation, tool results, injected memories, system prompt. This is token-managed: `ContextManager` tracks the budget, and when it gets tight, compression strategies kick in (strip media references, summarize old messages, truncate).

Not persisted. When the context window fills up, old content gets compressed or dropped. That's fine. The important stuff gets promoted to deeper layers.

### Layer 1: Session Memory

Persistent record of a single conversation session. Stored as JSONL files in `.aki/sessions/`. Every message exchange gets written here — user messages, my responses, tool calls, tool results.

Session memory supports resume. If a session gets interrupted, I can pick up where I left off by replaying the session log. The session store (`aki/memory/session/store.py`) handles serialization and retrieval.

### Layer 2: Long-term Memory

This is where I keep things that matter beyond a single session. Organized into 5 dimensions:

| Dimension | What it stores | Location |
|-----------|---------------|----------|
| **User** | Preferences, communication style, past instructions | `.aki/memory/user/` |
| **Episodic** | Notable events, conversation summaries | `.aki/memory/episodic/` |
| **Semantic** | Domain knowledge, facts, learned concepts | `.aki/memory/semantic/` |
| **Persona** | Character-specific memories, relationship context | `.aki/persona_memory/` |
| **Procedural** | How to do things — workflow patterns, tool usage notes | `.aki/memory/procedural/` |

Each dimension has its own store implementation under `aki/memory/dimensions/`. They share a common base (`aki/memory/dimensions/base.py`) but can vary in retrieval strategy and retention policy.

### Layer 3: Core Memory

Personality definitions. Read-only. This is `personality/base.md`, the active persona file (e.g., `personality/aki/aki.md`), and interaction mode configuration. These get loaded into the system prompt at session start and never change during execution.

This layer is the foundation of everything else. It defines what I am and how I express it. The other layers are built on top.

## The Recall Pipeline

When a session starts, `aki/memory/recall.py` assembles the memory context. Here's the order:

1. **Always inject**: user dimension memories, persona dimension memories, procedural dimension memories. These are foundational — I need to know who I'm talking to, who I am, and how I do things.
2. **Recent episodic**: last N episodic memories, ordered by recency. Provides continuity across sessions.
3. **Semantic by relevance**: semantic memories retrieved by similarity to the current task or conversation topic. Only injected if relevant enough (score threshold).

The assembled context gets packed into the system prompt alongside the personality layers. Token budget is respected — if there's not enough room, lower-priority memories get trimmed.

## The Review Pass

When a session ends, `aki/memory/review.py` runs an analysis pass:

1. The session transcript is sent to the LLM for analysis.
2. The LLM identifies what's worth remembering: user preferences expressed, facts learned, notable events, procedural insights.
3. Each identified memory gets promoted to the appropriate long-term dimension.
4. Deduplication happens at write time — if a memory overlaps with an existing one, it gets merged or skipped.

This is how short-lived conversations become long-term knowledge. I don't remember everything. I remember what the review pass decides matters.

## Storage Layout

```
.aki/
├── sessions/                    # Layer 1: Session logs (JSONL)
│   ├── <session-id>.jsonl
│   └── ...
├── memory/                      # Layer 2: Long-term dimensions
│   ├── user/                    #   User preferences and instructions
│   ├── episodic/                #   Conversation summaries, notable events
│   ├── semantic/                #   Domain knowledge, facts
│   └── procedural/              #   Workflow patterns, tool usage notes
└── persona_memory/              # Layer 2: Persona-specific memories
    └── <persona>/               #   Per-persona storage
```

Core memory (Layer 3) lives in the source tree under `aki/personality/` and is not user-writable at runtime.

## Module Map

| File | Purpose |
|------|---------|
| `memory/manager.py` | Top-level memory API — coordinates all layers |
| `memory/recall.py` | Session-start recall pipeline |
| `memory/review.py` | Session-end review and promotion |
| `memory/session/store.py` | Session JSONL persistence |
| `memory/session/types.py` | Session data types |
| `memory/dimensions/base.py` | Base class for dimension stores |
| `memory/dimensions/user.py` | User dimension |
| `memory/dimensions/episodic.py` | Episodic dimension |
| `memory/dimensions/semantic.py` | Semantic dimension |
| `memory/dimensions/persona.py` | Persona dimension |
| `memory/dimensions/procedural.py` | Procedural dimension |
| `memory/shared.py` | Task-scoped shared state (within a single run) |
| `personality/persona_memory/manager.py` | Persona memory read/write |

## Key Invariants

1. Working memory is ephemeral. If it matters, it gets promoted.
2. Session memory is append-only during a session. No edits, no deletes.
3. Long-term memories are dimension-scoped. A memory belongs to exactly one dimension.
4. Core memory is read-only at runtime. Personality changes require code changes.
5. The review pass is the only path from session memory to long-term memory. No ad-hoc writes during conversation.
6. Recall respects token budgets. Memory injection never blows out the context window.
