# Agent Role Policy Guide

## Goal

Aki leverages a single core `UniversalAgent` engine and orchestrates tasks entirely through functional `Roles`. This eliminates agent explosion and rigid class hierarchies.

This design enforces:

1. **Tools** own execution logic.
2. **Roles** own orchestration policy, persona boundaries, and tool access limits.
3. **UniversalAgent** provides the raw Reasoning and Acting loop.

## Core Model

### Tools

Tools are executors. They do concrete work and produce artifacts.

Examples:

- `audio_extract`
- `audio_vad`
- `transcribe`
- `subtitle_translate`
- `subtitle_proofread`
- `subtitle_edit`
- `vision_analyze`

### Roles

Roles are orchestration policies. They choose tool sequence and quality gates, but do not duplicate
tool business logic.

Runtime role source of truth:

- Runtime role module: `aki/agent/roles.py`
- Role blueprints: `aki/skills/agent-creation/Skill.md` frontmatter (`roles` block)

Primary subtitle workflow roles:

- `Orchestrator`
- `MediaExtractor`
- `Localizer`
- `QAEditor`
- `Generalist`

### Agents

There are no rigid agent classes anymore (like `translation.py` or `audio.py`). Instead, Aki relies on specialized configurations of the `UniversalAgent`:

- **Orchestrator**: High-level planner that discovers skills first, then reads skill bodies and spawns temporary workers.
- **Workers**: Transient agents instantiated directly via `delegate_to_worker` with strictly delimited rules (like `MediaExtractor`, `Localizer`, `QAEditor`, `Generalist`).

For subtitle translation, the Orchestrator should load:

1. `skills_search(query=...)` to find relevant skills
2. `read_skill("subtitle-translation")` for workflow execution phases (if matched)
3. `read_skill("agent-creation")` for role contracts before delegation
4. fallback delegation through `Generalist` or dynamic role creation when no skill matches

## Deterministic Delegation (Updated)

For subtitle workflows, `delegate_to_worker` provides deterministic execution paths for key workers:

1. **MediaExtractor**
   - Fixed execution order: `audio_extract -> audio_vad -> transcribe`.
   - Uses full VAD `chunks` manifest for ASR timing continuity.
2. **Localizer**
   - Normalizes subtitle payload schema before translation (`index/start_time/end_time/text`).
   - Preserves full segment list for downstream QA.
3. **QAEditor**
   - Accepts either `translated_subtitles` or `subtitle_file_path`.
   - Writes final timestamped SRT deterministically via `srt_write`.

## Role Semantics

### `Orchestrator`

- Purpose: discover skills, read matched skills, plan execution, and delegate only.
- Typical tools: `skills_search`, `read_skill`, `delegate_to_worker`.
- Constraint: should not perform media extraction or translation directly.

### `MediaExtractor`

- Purpose: produce transcription artifacts from media.
- Typical tools: `audio_extract` -> `audio_vad` -> `transcribe`.

### `Localizer`

- Purpose: translate and subtitle-edit ordered subtitle segments.
- Typical tools: `subtitle_translate` -> `subtitle_edit`.

### `QAEditor`

- Purpose: proofread translated subtitles and produce final SRT.
- Typical tools: `subtitle_proofread` -> `srt_write`.

### `Generalist`

- Purpose: fallback execution for open-ended text and basic IO tasks.
- Typical tools: `translate_text`, `proofread_text`, `file_*`, `pdf_read`, `web_*`, `srt_*`.

## Subtitle Workflow (Current)

For subtitle generation:

1. `delegate_to_worker(MediaExtractor)`  
   internal order: `audio_extract` -> `audio_vad` -> `transcribe`
2. `delegate_to_worker(Localizer)`  
   internal order: `subtitle_translate` -> `subtitle_edit`
3. `delegate_to_worker(QAEditor)`  
   internal order: `subtitle_proofread` -> `srt_write`

## Quality Profiles

The pipeline now minimizes human parameter tuning with profile defaults:

- `fast`
- `balanced` (default)
- `high_quality`

These profiles control internal knobs like:

- VAD segment/chunk settings
- frame extraction interval/count
- subtitle split threshold
- proofread batch size
- editor context window

CLI entrypoint:

```bash
aki subtitle <video_path> --source en --target zh --quality balanced
```

## Key Invariants

1. Roles never re-implement tool logic.
2. Proofreader only reviews and suggests.
3. Editor is the only stage that mutates translated subtitles.
4. Public agent names and CLI/MCP entrypoints stay stable.
5. Subtitle pipeline completion must be based on QAEditor returning a concrete `.srt` output.
6. Chunk/segment processing must preserve full timeline coverage (not just early segments).
7. Missing skill lookup must not dead-end orchestration; fallback delegation remains available.
8. Dynamic worker roles cannot include orchestration-only tools (`delegate_to_worker`, `read_skill`, `skills_search`).

## How to Create Additional Agents (Beyond the Current Five)

This architecture supports new role types without adding new hardcoded agent engine classes.

### 1. Add role blueprint in skill frontmatter

Edit `aki/skills/agent-creation/Skill.md` and add a new entry under `roles` with:

1. `name`
2. `persona`
3. `system_prompt`
4. `allowed_tools`

Example:

```yaml
roles:
  TerminologyReviewer:
    name: TerminologyReviewer
    persona: You ensure domain terms remain consistent across subtitle segments.
    system_prompt: |
      You review translated subtitles for terminology consistency and return updated segments.
    allowed_tools:
      - subtitle_proofread
      - subtitle_edit
```

### 2. Ensure tool availability

Every tool listed in `allowed_tools` must be registered in the runtime tool registry and callable in worker context.

### 3. Wire delegation path

If the role should be callable via `delegate_to_worker`, update `aki/tools/delegate_to_worker.py`:

1. Import the new role from `aki/agent/roles.py`
2. Add it to `_ROLE_DIRECTORY`
3. Add deterministic execution handling if the role needs a fixed internal pipeline

### Runtime dynamic role creation (no code changes)

`delegate_to_worker` also supports runtime role creation for unknown `worker_role` values:

1. Provide `worker_persona`
2. Provide `worker_system_prompt`
3. Provide `worker_allowed_tools` (non-empty, registered tools only)
4. Do not include orchestration-only tools (`delegate_to_worker`, `read_skill`, `skills_search`)

### 4. Add workflow usage

Update workflow skill instructions (for example `aki/skills/subtitle-translation/SKILL.md`) so the Orchestrator knows when to delegate to the new role.

### 5. Runtime loading behavior

`aki/agent/roles.py` loads role blueprints from `agent-creation` frontmatter at runtime.  
After blueprint + delegation wiring are in place, the `UniversalAgent` can execute the new role directly.

## Memory Boundary (Updated)

1. Short-term memory stores per-task runtime context and multimodal artifacts.
2. Long-term memory stores reusable semantic memory:
   - `user_instruction`
   - `domain_knowledge`
   - `web_knowledge`
3. Knowledge RAG index remains separate from long-term memory index.
4. Agent observation can fuse short-term and long-term memory context.
