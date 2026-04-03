# Receipt: How the Agent Finishes Subtitle Translation

Date: 2026-02-28

## Goal

Document the agent behavior and end-to-end execution path for completing a subtitle translation task.

This receipt focuses on:

1. Input
2. Output
3. Middle process
4. Implementation details

## Input

### User instruction

```text
You are the Orchestrator. Read the subtitle-translation skill. Using the skill, translate the video at /Users/jiaenliu/Documents/Codes/Aki/frozen采访.mp4 to Chinese (zh).
```

### Command used

```bash
uv run aki run "You are the Orchestrator. Read the subtitle-translation skill. Using the skill, translate the video at /Users/jiaenliu/Documents/Codes/Aki/frozen采访.mp4 to Chinese (zh)." -v
```

## Output

### Final task result

`ToolResult(success=True, data={"worker_output": "<final_srt_path>"}, error=None, metadata={})`

### Final subtitle artifact

`/Users/jiaenliu/Documents/Codes/Aki/outputs/task_1772243895_47915ea2/final_subtitles.srt`

### Execution log

```
╭────────────────────────────────── Aki ───────────────────────────────────╮
│ Task: You are the Orchestrator. Read the subtitle-translation skill. Using   │
│ the skill, translate the video at                                            │
│ /Users/jiaenliu/Documents/Codes/Aki/frozen采访.mp4 to Chinese (zh).      │
│ Agent: main                                                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
Verbose mode enabled
╭────────────────────── 🔵 ORCHESTRATOR Agent (depth=0) ───────────────────────╮
│ You are the Orchestrator. Read the subtitle-translation skill. Using the     │
│ skill, translate the video at                                                │
│ /Users/jiaenliu/Documents/Codes/Aki/frozen采访.mp4 to Chinese (zh).      │
╰──────────────────────────────────────────────────────────────────────────────╯

  ─── Observe ───

  ─── Think ───
    💭 Reasoning: To understand the complete workflow and steps involved in 
translating subtitles, I need to read the instructions for the 
'subtitle-translation' skill.
    📋 Decision: invoke_tool → read_skill

  ─── Act ───
    🔧 invoke_tool → read_skill
    params: {'skill_name': 'subtitle-translation'}
    → Result: success=True data={'skill_content': '---\nname: 
subtitle-translation\ndescription: Translates the audio/video into localized 
subtitle files using specialized agent delegates.\n---\n\n# Subtitle Transl...

  ─── Reflect ───
    Iteration 1: Continue

  ─── Observe ───

  ─── Think ───
    💭 Reasoning: To proceed with the subtitle translation task, I need to set 
up the necessary agents. This requires reading the 'agent-creation' skill to 
understand how to properly establish roles for Orchestrator, MediaExtractor, 
Localizer, and QAEditor.
    📋 Decision: invoke_tool → read_skill

  ─── Act ───
    🔧 invoke_tool → read_skill
    params: {'skill_name': 'agent-creation'}
    → Result: success=True data={'skill_content': "---\nname: 
agent-creation\ndescription: Create Orchestrator and worker agent roles for 
subtitle workflows with explicit personas, prompts, and allowed tool boundar...

  ─── Reflect ───
    Iteration 2: Continue

  ─── Observe ───

  ─── Think ───
    💭 Reasoning: Delegate the task of extracting audio, running VAD, and 
transcribing to produce the English transcription to the MediaExtractor worker.
    📋 Decision: invoke_tool → delegate_to_worker

  ─── Act ───
    🔧 invoke_tool → delegate_to_worker
    params: {'worker_role': 'MediaExtractor', 'task_instruction': 'Extract audio
from the video file, run Voice Activity Detection (VAD) to segment the audio, 
and...
    → Result: success=True data={'worker_output': {'text': 'The phase we came to
see, and this man woke up and showed a lot of violence. And you said to me just 
before you went into the match, "You\'re gonna destro...

  ─── Reflect ───
    Iteration 3: Continue

  ─── Observe ───

  ─── Think ───
    💭 Reasoning: To proceed with the subtitle translation workflow, the 
transcription needs to be localized into the target language, Chinese (zh). The 
'Localizer' role is responsible for this phase, translating the provided English
transcription into Chinese.
    📋 Decision: invoke_tool → delegate_to_worker

  ─── Act ───
    🔧 invoke_tool → delegate_to_worker
    params: {'worker_role': 'Localizer', 'task_instruction': 'Translate the 
provided transcription from English to Chinese (zh).', 'context_data': 
{'transcription...
    → Result: success=True data={'worker_output': [{'index': 1, 'start_time': 
'00:00:00,005', 'end_time': '00:00:11,505', 'text': 
'我们来看这个阶段，这个人醒来后表现得非常激烈。你在比赛前对我说，“你会摧毁它。”
虽然你用的不是这个词，但你已经准备好了，对吧？在昨天之后你有话要证明。', 
'src_...

  ─── Reflect ───
    Iteration 4: Continue

  ─── Observe ───

  ─── Think ───
    💭 Reasoning: The translated subtitles need to be reviewed for accuracy, 
consistency, and proper timing. The QAEditor will ensure that the subtitles are 
ready for final output.
    📋 Decision: invoke_tool → delegate_to_worker

  ─── Act ───
    🔧 invoke_tool → delegate_to_worker
    params: {'worker_role': 'QAEditor', 'task_instruction': 'Review the 
translated subtitles for accuracy and consistency, ensure proper timing and 
formatting for...
    → Result: success=True data={'worker_output': 
'/Users/jiaenliu/Documents/Codes/Aki/outputs/task_1772243895_47915ea2/final_
subtitles.srt'} error=None metadata={}

  ─── Reflect ───
    Iteration 5: Complete
✓ [Orchestrator] Completed: success=True data={'worker_output': 
'/Users/jiaenliu/Documents/Codes/Aki/outputs/task_1772243895_47915ea2/final_
subtitles.srt'} error=None metadata={}


Result:
ToolResult(
    success=True,
    data={
        'worker_output': 
'/Users/jiaenliu/Documents/Codes/Aki/outputs/task_1772243895_47915ea2/final_
subtitles.srt'
    },
    error=None,
    metadata={}
)
```

## Middle Process (Agent Behavior)

The Orchestrator follows skill-driven, phase-based delegation:

1. Reads workflow skill: `read_skill("subtitle-translation")`
2. Reads role contract skill: `read_skill("agent-creation")`
3. Delegates media phase: `delegate_to_worker(worker_role="MediaExtractor", ...)`
4. Delegates localization phase: `delegate_to_worker(worker_role="Localizer", ...)`
5. Delegates QA/output phase: `delegate_to_worker(worker_role="QAEditor", ...)`
6. Completes only after QAEditor returns a concrete `.srt` output path

Observed verbose sequence in run log:

1. `subtitle-translation` skill loaded successfully
2. `agent-creation` skill loaded successfully
3. `MediaExtractor` returned transcription payload
4. `Localizer` returned translated subtitle list
5. `QAEditor` returned final SRT path
6. Orchestrator reflected completion and exited successfully

## Implementation Details

### Skill contracts

1. Workflow skill: `aki/skills/subtitle-translation/SKILL.md`
2. Role contract skill: `aki/skills/agent-creation/Skill.md`

### Runtime role module

1. Role models/loaders: `aki/agent/roles.py`
2. Role blueprints: `roles` frontmatter in `aki/skills/agent-creation/Skill.md`

### Role responsibilities

1. `Orchestrator`
   - Reads skills
   - Delegates phases
   - Assembles and returns final result
2. `MediaExtractor`
   - Runs media extraction/transcription flow
   - Produces transcript or subtitle-ready segments
3. `Localizer`
   - Translates content to target language (`zh`)
   - Returns normalized subtitle entries
4. `QAEditor`
   - Proofreads translated subtitles
   - Writes final `.srt` file

### Tool-level behavior used in this run

1. `read_skill`
   - Loads full skill body by skill name
2. `delegate_to_worker`
   - Invokes worker-role-specific execution path
3. Worker internals
   - `MediaExtractor`: audio extraction + VAD + transcription
   - `Localizer`: subtitle translation/editing
   - `QAEditor`: subtitle proofreading + SRT write

### Completion criteria

The task is considered complete when:

1. QA stage succeeds
2. A concrete `.srt` path is returned
3. Orchestrator emits final successful `ToolResult`

## Repro Checklist

To reproduce this task behavior:

1. Ensure required environment variables/providers are configured.
2. Confirm source media exists at target path.
3. Run the exact command in the Input section.
4. Inspect verbose output and final `ToolResult`.
5. Verify generated `final_subtitles.srt` path in `outputs/task_*`.
