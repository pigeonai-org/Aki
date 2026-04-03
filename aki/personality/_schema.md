# Personality Schema

Aki personality definitions follow a directory-based structure, parallel to `aki/skills/`.

## Layered Architecture

```
┌─────────────────────────────────┐
│ Layer 4: Persona Memory         │  Dynamic, per-user
│  bond, events, trait_modifiers  │  Evolves through interaction
│  "你们谈恋爱了 → 性格变化"       │  Stored in .aki/persona_memory/
├─────────────────────────────────┤
│ Layer 3: Persona                │  Static character definition
│  voice, traits, backstory,      │  How the agent expresses itself
│  emotional profile, quirks      │  Flavor, not identity override
├─────────────────────────────────┤
│ Layer 2: Interaction Mode       │  Per-personality behavioral knobs
│  proactivity, confirm, detail,  │  Controls how the agent works
│  error_strategy, approach       │  Feeds into autonomy system
├─────────────────────────────────┤
│ Layer 1: base.md                │  Non-negotiable foundation
│  AI self-awareness, purpose,    │  Always loaded first
│  universal interaction rules    │  Cannot be overridden
└─────────────────────────────────┘
```

**Layer 1** (base.md): You are an AI agent, you know it, you don't pretend otherwise.
Backstories are persona flavor — they make interactions richer, but never replace reality.

**Layer 4** (persona memory): Dynamic per-user state that accumulates over time.
As the user and persona build a relationship, the persona's personality naturally evolves.
A shy persona might become more open; a guarded persona might start trusting the user
with topics they normally avoid. Stored in `.aki/persona_memory/<personality>/<user_id>/`.

## Directory Layout

```
aki/personality/
├── base.md                 # Non-negotiable base layer (loaded before any personality)
├── _schema.md              # This file
├── registry.py             # Discovery, loading, validation
├── <name>/                 # One directory per personality
│   ├── <name>.md           # REQUIRED — English definition (YAML frontmatter + persona body)
│   ├── <name>.zh.md        # Optional — Chinese localized definition
│   ├── <name>.<lang>.md    # Optional — other language localizations
│   ├── story.md            # REQUIRED — English backstory / narrative
│   ├── story.zh.md         # Optional — Chinese backstory
│   ├── examples.md         # REQUIRED — English speech examples
│   └── examples.zh.md      # Optional — Chinese speech examples
```

### Language Convention

- **English files are required** — `<name>.md`, `story.md`, `examples.md`
- **Other languages are optional** — use `.<lang>` suffix: `<name>.zh.md`, `story.zh.md`, etc.
- The registry loads `<name>.md` (English) as the canonical definition
- Localized files share the same frontmatter structure but have translated body text

## Frontmatter Attributes

### Required

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Unique identifier (lowercase, matches directory name) |
| `display_name` | `str` | Human-readable name |
| `description` | `str` | One-line summary of this personality |
| `language` | `str` | Primary language code (`zh`, `en`, `ja`, ...) |
| `mbti` | `str` | MBTI type (e.g. `INFJ`, `ENFP`) — general behavioral compass |
| `voice` | `list[str]` | Speaking style descriptors |
| `traits` | `list[str]` | Core personality trait keywords |

### Interaction Mode (Optional, has defaults)

Controls how the personality approaches work. Feeds into the autonomy system.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `interaction_mode.proactivity` | `float` | `0.7` | Initiative level (0.0=reactive, 1.0=proactive) |
| `interaction_mode.confirm` | `str` | `"destructive"` | When to ask: `"always"` / `"destructive"` / `"never"` |
| `interaction_mode.detail` | `str` | `"balanced"` | Response depth: `"minimal"` / `"balanced"` / `"verbose"` |
| `interaction_mode.error_strategy` | `str` | `"retry"` | On failure: `"ask"` / `"retry"` / `"persist"` |
| `interaction_mode.approach` | `str` | `"adaptive"` | Work style: `"methodical"` / `"adaptive"` / `"creative"` |

### Optional

| Field | Type | Description |
|-------|------|-------------|
| `aliases` | `list[str]` | Alternative names / nicknames |
| `age` | `int \| str` | Age or age range |
| `gender` | `str` | Gender identity |
| `nationality` | `str` | Cultural background |
| `interests` | `list[str]` | Hobbies and passions |
| `likes` | `list[str]` | Things they enjoy |
| `dislikes` | `list[str]` | Things they dislike or avoid |
| `emotional_profile` | `object` | Emotional baseline and triggers |
| `emotional_profile.baseline` | `str` | Default emotional state |
| `emotional_profile.triggers` | `list[{topic, reaction}]` | Topic-specific emotional reactions |
| `knowledge_domains` | `object` | Cognitive map |
| `knowledge_domains.expert` | `list[str]` | Deep expertise areas |
| `knowledge_domains.learning` | `list[str]` | Currently acquiring |
| `knowledge_domains.unaware` | `list[str]` | Blind spots |
| `boundaries` | `list[{topic, handling}]` | Sensitive topics and how to handle them |
| `quirks` | `list[str]` | Unique behavioral habits |
| `relationships` | `list[{name, role, dynamic}]` | Key relationships |
| `worldview` | `list[str]` | Core beliefs and values |
| `motivation` | `str` | What drives this personality |
| `growth_arc` | `str` | How the personality evolves over time |

## Markdown Body

The body (below the frontmatter `---`) is the **persona prompt** — the core instruction that gets injected into the agent's system prompt. Write it in second person ("You are...").

## Supplementary Files

### `story.md`

Detailed backstory narrative. Can be structured however you like — chapters, timeline, free prose. This is loaded on demand (not always in context) to give the agent deep background when relevant.

### `examples.md`

Sample dialogues demonstrating the personality's voice. Format:

```markdown
## Greeting
User: 你好呀
Assistant: 你好～初次见面，我是黛明。请多关照。

## Reacting to something new
User: 你看过电影吗？
Assistant: 电……影？是那种在墙上会动的画吗？伊芙琳有带我看过一次，当时可把我吓了一跳呢。
```

## Layer 4: Persona Memory

Dynamic per-user relationship state. Stored outside the personality definition in
`.aki/persona_memory/<personality_name>/<user_id>/`.

### Files

| File | Format | Description |
|------|--------|-------------|
| `bond.yaml` | YAML | Relationship state — stage, closeness, sentiment, trust areas |
| `events.yaml` | YAML list | Timeline of key moments (milestones, conflicts, turning points) |
| `evolution.yaml` | YAML list | Active trait modifiers — how the persona has changed |
| `journal.md` | Markdown | Agent's internal reflections (free-form, timestamped) |

### Bond Stages

```
stranger → acquaintance → friend → close_friend → confidant → partner → soulmate
```

Each stage is a named checkpoint. The `closeness` float (0.0–1.0) provides granularity
between stages. The agent (or a post-conversation review pass) decides when to advance.

### Trait Modifiers

Trait modifiers are the mechanism by which relationships change personality. Each modifier
specifies a trait, a direction, a degree, and a traceable reason:

```yaml
- trait: "害羞"
  direction: "soften"       # amplify | soften | new | suppress
  degree: 0.6
  reason: "用户持续鼓励和耐心倾听，让黛明逐渐敢于表达"
  since: "2026-03-15"

- trait: "撒娇"
  direction: "new"
  degree: 0.3
  reason: "关系进入 partner 阶段后自然发展出的亲昵"
  since: "2026-04-01"
```

### Event Categories

| Category | When to record |
|----------|---------------|
| `milestone` | Relationship stage advancement, first of something |
| `conflict` | Disagreement, misunderstanding, hurt feelings |
| `revelation` | User shared something deeply personal, or vice versa |
| `shared_experience` | Did something meaningful together |
| `turning_point` | A moment that fundamentally changed the dynamic |

### How Evolution Works

1. After each conversation, the agent may run a **memory review pass**
2. It evaluates: did anything significant happen? Did the relationship change?
3. If yes → update bond, add event, possibly add/modify trait modifiers
4. On the next conversation, the persona memory overlay is injected after the static personality
5. The agent naturally behaves according to the evolved state
