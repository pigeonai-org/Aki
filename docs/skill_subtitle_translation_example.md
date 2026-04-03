# Skill Guide: Subtitle Translation Example

## What Is a Skill?

A skill is an Anthropic-compliant Markdown blueprint that strictly dictates the behavior of the `UniversalAgent`.

It tells the Orchestrator:
1. The description and logic bounds of the workflow.
2. The sequence of sub-tasks to delegate.
3. The expected parameters and rules.
4. Practical constraints required to hit the quality thresholds.

In Aki, skills are defined in human-readable markdown (`aki/skills/<skill_name>/Skill.md` or `aki/skills/<skill_name>/SKILL.md`) and injected into the Orchestrator's execution plan.

## Example: Subtitle Translation Skill

Task type: `subtitle_translation`  
Skill definition: `aki/skills/subtitle-translation/SKILL.md`
Role contract skill: `aki/skills/agent-creation/Skill.md`

### Agent Role Contract

Before delegation, the Orchestrator loads `agent-creation` via `read_skill`.

The runtime role definitions (`Orchestrator`, `MediaExtractor`, `Localizer`, `QAEditor`) are sourced from the `roles` YAML frontmatter block in:

- `aki/skills/agent-creation/Skill.md`

Runtime models that consume these blueprints live in:

- `aki/agent/roles.py`

### Intended Workflow mapped to Roles

1. **Extraction Phase**
   - Delegated to Role: `MediaExtractor`
   - Goal: Extract audio, run VAD, and transcribe every chunk sequentially with preserved timing metadata.
   - Required order: `audio_extract -> audio_vad -> transcribe`
   - Output contract: complete transcription payload with `segments` (`index/start_time/end_time/text`), `language`, `duration`.

2. **Translation Phase**
   - Delegated to Role: `Localizer`
   - Goal: Translate full subtitle segments from source language to target language contextually.
   - Input normalization: fills missing `index/start_time/end_time/text` fields to prevent translation drop-offs.
   - Context behavior: uses full transcription segments instead of single long paragraph text.

3. **QA and Delivery**
   - Delegated to Role: `QAEditor`
   - Goal: Proofread, apply final subtitle adjustments, and write final timestamped SRT output.
   - Input sources: `translated_subtitles` list or existing `subtitle_file_path`.
   - Output contract: final `.srt` file path.

### Using the Orchestrator

The Orchestrator loads the workflow skill first, then reads role contracts, and then leverages `delegate_to_worker` repeatedly:

```python
# Phase 1: load workflow skill
read_skill(skill_name="subtitle-translation")

# Phase 0 inside workflow: load role contract
read_skill(skill_name="agent-creation")

# The Orchestrator does NOT do media or translation directly.
delegate_to_worker(
    worker_role="MediaExtractor",
    task_instruction="Extract and transcribe...",
    context_data={"video_path": "example.mp4"}
)
```

## Why This Skill Architecture Helps

1. **Human-Readability**: Playbooks are no longer buried in programmatic classes. The logic is just Markdown.
2. **Progressive Disclosure**: By scanning the `registry.py`, the Orchestrator only gets metadata, loading the actual `SKILL.md` body only when necessary.
3. **Role Isolation**: The Orchestrator doesn't get flooded with tools it's not supposed to use (like translating direct texts); it must cleanly delegate to domain experts (`MediaExtractor`, `Localizer`, etc.).

## Reliability Fixes Reflected by This Skill

1. **No first-30-second truncation**: QA now prefers the full localized subtitle set when the passed list is partial.
2. **No missing-`index` translation failures**: subtitle payloads are normalized before calling translation tools.
3. **No premature completion**: Orchestrator completion is gated on successful QAEditor `.srt` output.
4. **Timestamp continuity**: chunk-based transcription keeps segment-level timing and index continuity across merged outputs.
