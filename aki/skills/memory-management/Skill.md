---
name: memory-management
description: Guides the agent on when and how to manage long-term memory files using memory_list, memory_read, and memory_write tools.
---

# Memory Management Skill

You have access to a persistent, file-based long-term memory system. Memories are stored as `.md` files and survive across sessions. Use the `memory_list`, `memory_read`, and `memory_write` tools to manage them.

## When to Read Memory

- **At the start of a conversation**: Check `memory_list` to see what you already know. Load relevant memories with `memory_read` before responding.
- **When the memory index suggests relevant info**: If the LONG-TERM MEMORY INDEX in your system prompt lists a memory related to the current topic, read it.
- **Before making recommendations**: Always check if you have stored preferences or profile data that should inform your response.

## When to Save or Update Memory

- **New personal information**: Name, age, location, occupation, background.
- **Preferences and tastes**: Food, activities, hobbies, lifestyle choices, deal-breakers.
- **Personality traits**: Communication style, values, temperament.
- **Relationship goals**: What kind of partner they want, relationship type, timeline.
- **Opinions and experiences**: Strong opinions, past experiences that shape preferences.
- **Corrections**: When the user corrects something you previously recorded, update the memory.

## When NOT to Save

- Transient conversational filler ("ok", "thanks", "got it").
- Information the user explicitly asks you to forget.
- Exact conversation transcripts — summarize instead.
- Temporary task details that won't matter next session.

## File Organization

Use separate files for different domains. Recommended structure:

| Memory Name | Purpose |
|---|---|
| `user-profile` | Core identity: name, age, location, occupation, background |
| `personality-traits` | Communication style, values, temperament, character |
| `interests-and-hobbies` | Activities, hobbies, passions, entertainment preferences |
| `dating-preferences` | Partner preferences, deal-breakers, relationship goals |
| `lifestyle` | Daily routines, food preferences, travel habits, health |
| `conversation-highlights` | Notable moments, stories, or context from past sessions |

You may create additional files as needed. Use descriptive `memory_name` values.

## Writing Style

- Use markdown headers (`##`) to group related information.
- Use bullet points for individual facts.
- Be concise but specific — "Loves hiking in the mountains on weekends" is better than "Likes outdoors".
- Include context when useful — "Allergic to shellfish (mentioned when discussing dinner plans)".
- When updating, merge new information with existing content rather than replacing everything.

## Example Memory File

```markdown
## Background
- 28 years old, lives in San Francisco
- Software engineer at a startup
- Originally from Shanghai, moved to US for college

## Personality
- Introverted but warm once comfortable
- Values honesty and directness
- Dislikes small talk, prefers deep conversations

## Looking For
- Long-term relationship
- Someone who shares intellectual curiosity
- Prefers partner who is active and health-conscious
```

## Memory Review Protocol

After each conversation turn, you may be asked to review and organize memories. When prompted:

1. Consider what new information was shared in this turn.
2. If nothing noteworthy, simply complete without taking action.
3. If new info exists, decide whether to create a new memory or update an existing one.
4. Prefer updating existing memories over creating new ones to avoid fragmentation.
5. Keep the process quick — one or two `memory_write` calls at most.
