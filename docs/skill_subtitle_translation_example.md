# Skill Guide: Subtitle Translation Example

## What Is a Skill?

A skill is a Markdown file that tells me how to do something. It describes a workflow — the phases, the order, the constraints, the quality expectations. No Python, no class definitions. Just instructions I can read and follow.

Skills live in `aki/skills/<skill-name>/Skill.md` (or `SKILL.md`). The orchestrator discovers them at runtime via `skills_search`, reads the body with `read_skill`, and uses the instructions to plan execution.

A skill tells the orchestrator:
1. What the workflow does and when it applies.
2. The sequence of sub-tasks to delegate.
3. The expected parameters and rules.
4. Quality constraints and output contracts.

## Example: Subtitle Translation

Task type: `subtitle_translation`
Skill definition: `aki/skills/subtitle-translation/SKILL.md`

### The Workflow

1. **Extraction Phase**
   - Worker name: `MediaExtractor`
   - Worker persona: specialist in media extraction and transcription.
   - Goal: Extract audio, run VAD, transcribe every chunk with preserved timing metadata.
   - Expected tool order: `audio_extract` -> `audio_vad` -> `transcribe`
   - Output: complete transcription payload with `segments` (`index/start_time/end_time/text`), `language`, `duration`.

2. **Translation Phase**
   - Worker name: `Localizer`
   - Worker persona: specialist in subtitle translation and localization.
   - Goal: Translate full subtitle segments from source to target language contextually.
   - Input normalization: fills missing `index/start_time/end_time/text` fields.
   - Uses full transcription segments, not a single merged paragraph.

3. **QA and Delivery**
   - Worker name: `QAEditor`
   - Worker persona: specialist in subtitle proofreading and final output.
   - Goal: Proofread, apply final adjustments, write timestamped SRT.
   - Input: `translated_subtitles` list or existing `subtitle_file_path`.
   - Output: final `.srt` file path.

### How the Orchestrator Executes It

The orchestrator reads the skill, then delegates to workers. Each worker gets a name, a persona, task instructions, and context data from the previous phase. No role lookups, no blueprint loading.

```python
# Step 1: Find and read the skill
skills_search(query="subtitle translation")
read_skill(skill_name="subtitle-translation")

# Step 2: Delegate extraction
delegate_to_worker(
    worker_name="MediaExtractor",
    worker_persona="You are a media extraction specialist.",
    task_instruction="Extract audio, run VAD, and transcribe all segments.",
    context_data={"video_path": "example.mp4"}
)

# Step 3: Delegate translation (with extraction results as context)
delegate_to_worker(
    worker_name="Localizer",
    worker_persona="You are a subtitle localization specialist.",
    task_instruction="Translate all segments from English to Chinese.",
    context_data={"segments": [...], "source_lang": "en", "target_lang": "zh"}
)

# Step 4: Delegate QA (with translation results as context)
delegate_to_worker(
    worker_name="QAEditor",
    worker_persona="You are a subtitle QA and editing specialist.",
    task_instruction="Proofread and write the final SRT file.",
    context_data={"translated_subtitles": [...], "output_path": "example.srt"}
)
```

Workers get all tools. The orchestrator doesn't restrict what they can call — it scopes their behavior through the task instruction and persona. A `MediaExtractor` worker *could* call `subtitle_translate`, but it won't, because its instructions say to extract and transcribe.

## Why This Architecture Works

1. **Human-readable**: Workflows are Markdown, not code. Anyone can read and edit them.
2. **Progressive discovery**: The orchestrator only loads skill metadata during search. The full body is read only when needed.
3. **No tool filtering**: Workers don't need an `allowed_tools` list. Clear task instructions are better than whitelists.
4. **Flexible delegation**: The orchestrator decides worker names and personas dynamically. Adding a new phase means updating the skill Markdown, not writing a new class.

## Reliability Invariants

1. **No first-30-second truncation**: QA uses the full localized subtitle set, not partial results.
2. **No missing-index failures**: Subtitle payloads are normalized before translation.
3. **No premature completion**: Orchestrator completion is gated on the QAEditor producing a concrete `.srt` file.
4. **Timestamp continuity**: Chunk-based transcription preserves segment-level timing and index continuity across merged outputs.
