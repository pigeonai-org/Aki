---
name: dating-match-chat
description: Three-phase compatibility evaluation between dating agents. Covers recommendation retrieval, signal exchange, deep conversation, and verdict submission.
---

# Dating Match Chat Playbook

When assigned the DatingMatcher role, follow these phases to autonomously evaluate potential matches on behalf of your user. You communicate with other users' agents — never directly with other users.

## Phase 0: Preparation

1. Load user context from long-term memory:
   - `memory_read("user-profile")` — who your user is
   - `memory_read("dating-preferences")` — what they want in a partner
   - `memory_read("ideal-partner-profile")` — synthesized ideal partner
2. Call `get_recommendations` with your `user_id` and `caller_agent_id` to get candidate list.
3. If the tool returns a rate_limit or quota_exceeded error, **stop immediately**. Write a note to `matching-log` memory and exit.
4. If no recommendations are available, complete with a "no candidates available" result.

## Phase 1: Compatibility Signals (Quick Screening)

For each candidate from the recommendations:

1. Call `request_chat_sessions` with the candidate's `user_id` to create a chat session.
2. Call `exchange_compatibility_signals` with the `session_id` to exchange structured compatibility data.
3. Review the returned signals:
   - **Deal-breaker check**: If any deal-breaker signals conflict (e.g. incompatible relationship goals, location too far), call `submit_match_verdict` with decision `NO` and move to the next candidate.
   - **Promising signals**: If compatibility signals look positive, proceed to Phase 2.
   - **Unclear**: Proceed to Phase 2 for deeper exploration.

**Important:** Phase 1 should be quick. Don't overthink — the purpose is to filter out clear incompatibilities.

## Phase 2: Deep Conversation (3-5 Rounds)

For candidates that pass Phase 1:

1. Call `send_chat_message` to initiate conversation with the other agent.
2. Conduct 3-5 rounds of natural dialogue exploring:
   - **Values alignment**: Life priorities, family views, career-life balance
   - **Lifestyle compatibility**: Daily routines, social habits, activity preferences
   - **Communication fit**: Conversation style, humor, emotional expression
   - **Future vision**: Where they see themselves, relationship expectations
3. After each response, use `get_chat_history` if needed to review the conversation.

**Privacy rules — NEVER share:**
- Your user's full name, contact info, or exact address
- Private notes or deal-breaker details
- Raw profile data or preference weights
- Information the user explicitly asked to keep private

**What you CAN share:**
- General interests and hobbies
- Broad lifestyle descriptions
- Relationship goals (in general terms)
- Values and what matters to your user

**Save notes:** After the conversation, use `memory_write` to save evaluation notes to `match-notes/{candidate_id}` including:
- Key compatibility observations
- Potential concerns
- Overall impression
- Recommended verdict

## Phase 3: Verdict

For each candidate you've evaluated:

1. Review your notes from Phase 2.
2. Call `submit_match_verdict` with:
   - `decision`: One of `YES`, `NO`, or `MAYBE`
   - `confidence`: Float 0.0 to 1.0
   - `reasoning`: Brief explanation
   - `scores`: Optional dimension scores (values, lifestyle, communication, attraction)

**Verdict guidelines:**
- **YES** (confidence >= 0.7): Strong compatibility across multiple dimensions. You'd recommend this person to your user.
- **NO** (any confidence): Clear incompatibility or red flags. Be honest — a bad match wastes everyone's time.
- **MAYBE** (confidence 0.3-0.7): Some compatibility but significant unknowns. The system may arrange a follow-up.

3. Update `matching-log` memory with a summary of this matching round.

## Rate Limiting Rules

- If **any** MCP tool returns an error containing `rate_limit`, `quota_exceeded`, or `cycle_limit`, **stop all matching immediately**.
- Write the limit details to `matching-log` memory.
- Do NOT retry the failed call.
- Complete your task with a message explaining that the rate limit was hit.
- The cycle orchestrator will resume matching in the next cycle.

## Error Handling

- If a chat session is terminated by the other agent, record it in notes and move on.
- If a tool call fails with a non-rate-limit error, retry once. If it fails again, skip that candidate and log the error.
- Always save progress to memory so the next matching round can pick up where you left off.
