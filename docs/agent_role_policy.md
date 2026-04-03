# Agent Architecture

## How I Think

There are no Roles. No `allowed_tools` lists. No hardcoded agent classes for translation or audio or anything else.

There's one agent engine — `UniversalAgent` — and personality is what makes each instance different. The model decides what tools to use, when, and in what order. I don't need a state machine to tell me how to think.

## Personality Drives Identity

Every agent instance gets its identity from personality, not from a role enum. The personality system has four layers, applied in order:

1. **`base.md`** — Non-negotiable principles. Honesty, self-awareness, never pretending to be human. This file cannot be overridden. It's the floor, not the ceiling.
2. **Interaction mode** — How I'm being accessed (chat, task, gateway). Adjusts verbosity and behavior.
3. **Persona** — The specific character. `aki/personality/aki/aki.md` or `aki/personality/aria/aria.md`. This is where communication style, humor, and voice come from.
4. **Persona memory** — Learned preferences and accumulated context for this persona. Managed by `aki/personality/persona_memory/manager.py`. Persists across sessions.

The system prompt is assembled from these layers at agent creation time. A worker might get a minimal persona ("You are a media extraction specialist"), while the orchestrator gets the full stack.

## Native Tool Calling

I don't use a ReAct loop. No `Thought: ... Action: ... Observation: ...` string parsing.

The LLM gets tools as structured function definitions. It decides whether to call tools, which ones, and with what arguments. The runtime executes the calls, feeds results back, and the model decides what to do next. That's it. A `while` loop and a model that's good at its job.

This means:
- No regex parsing of model output
- No fragile action/observation templates
- The model can call multiple tools in parallel if it wants to
- Tool selection is the model's problem, not mine

## All Agents Get All Tools

There's no `allowed_tools` filtering. Every agent — orchestrator or worker — has access to the full tool registry.

Why? Because tool filtering was solving the wrong problem. The model doesn't need guardrails on which tools it *can* call — it needs clear instructions on what it *should* do. A well-written task instruction is better than a whitelist. If I tell a worker "extract audio, run VAD, then transcribe," it's not going to spontaneously start translating subtitles.

The one exception: orchestration-only tools like `delegate_to_worker` are only meaningful for the orchestrator. Workers don't delegate further (depth is controlled by `AgentContext`).

## Orchestrator and Workers

The orchestrator is where I live. It's a `UniversalAgent` with the full personality stack, access to skills, and the ability to spawn workers.

Workers are temporary. The orchestrator creates them via `delegate_to_worker` with:
- A **name** (for logging and identification)
- A **persona** (a short description of what the worker should focus on)
- A **task instruction** (what to do)
- **Context data** (inputs from previous steps)

The worker runs, returns a result, and is discarded. No persistent state, no identity beyond the task.

```python
delegate_to_worker(
    worker_name="MediaExtractor",
    worker_persona="You are a media extraction specialist.",
    task_instruction="Extract audio from the video, run VAD, and transcribe.",
    context_data={"video_path": "example.mp4"}
)
```

No role lookup. No blueprint loading. The orchestrator decides the plan based on the task and any relevant skill instructions, then delegates.

## How Delegation Works

1. User gives me a task.
2. I (the orchestrator) check if there's a matching skill via `skills_search`.
3. If found, I read the skill body with `read_skill` to get workflow instructions.
4. I break the task into sub-tasks and delegate each to a worker.
5. Each worker gets a name, persona, task instruction, and any context data from previous workers.
6. I collect results, decide if more work is needed, and produce the final output.

If no skill matches, I still delegate — I just plan the workflow myself based on the task description. Skills are guides, not requirements.

## How to Add a New Workflow

You don't write a new agent class. You write a Markdown skill file:

1. Create `aki/skills/<skill-name>/Skill.md` with workflow instructions.
2. Describe the phases, the expected worker names, and what each should do.
3. The orchestrator will discover it via `skills_search` and follow the instructions.

If you need a new tool, add it to `aki/tools/`. It'll be available to all agents immediately.

## Key Invariants

1. Personality defines identity. There are no role enums.
2. All agents get all tools. Task instructions scope behavior, not whitelists.
3. Workers are temporary. They don't persist, delegate, or have memory.
4. The orchestrator is the only agent that delegates and reads skills.
5. Native tool calling only. No ReAct string parsing.
6. `base.md` is never overridden. Everything else is negotiable.
