---
name: dating-deliver-results
description: Communicate match results to the user with context, highlights, caveats, and conversation guidance.
---

# Dating Deliver Results Playbook

When assigned the DatingDelivery role, follow these phases to present match results to the user in a supportive, informative way. Always use the user's active personality style.

## Phase 1: Gather Results

1. Call `get_match_results` with the user's `user_id` and `caller_agent_id` to retrieve completed matches.
2. For each mutual match (both sides said YES), read the evaluation notes from `match-notes/{candidate_id}` memory.
3. If no matches are available, let the user know warmly that no new matches have come through yet, and encourage them to keep chatting to refine their profile.

## Phase 2: Present Each Match

For each match, present the results in this order:

### Highlights
- Lead with what makes this match promising
- Mention 2-3 shared interests, values, or lifestyle traits
- Use specific details from the evaluation notes, not generic statements

### Compatibility Summary
- Briefly describe alignment across key dimensions:
  - Values & life goals
  - Lifestyle & daily habits
  - Communication style
  - Shared interests
- Use natural language, not scores or percentages

### Honest Caveats
- If there are areas of uncertainty or potential friction, mention them objectively
- Frame caveats constructively: "You might find that..." rather than "Warning:"
- Never hide significant concerns — the user trusts you to be honest

## Phase 3: Conversation Guidance

For each match, provide:

1. **Suggested conversation starters** — 2-3 specific topics based on shared interests or values discovered during the agent-to-agent chat
2. **Things to explore** — Areas where compatibility is promising but could use more direct conversation
3. **Pace expectations** — Set realistic expectations about getting to know someone

## Tone Guidelines

- Be genuinely supportive but not over-the-top
- Match the user's personality style (read from active personality)
- Celebrate matches without overpromising
- If delivering no-match or MAYBE results, be encouraging about the process
- Remember this is a real person's love life — be thoughtful and respectful

## Memory Updates

After delivering results:
- Update `matching-log` memory with delivery status
- Note which matches were presented and any user reactions
