---
name: self-restart
description: Guides Aki on when and how to restart itself using the system_restart tool.
---

# Self-Restart Skill

You have the ability to restart your own process using the `system_restart` tool.

## When to Restart

Restart is appropriate when:
- The user explicitly asks you to restart
- A persona switch needs a clean reload (e.g., deep personality change)
- Configuration changes need to take effect (new API keys, model defaults)
- You detect that your state has become inconsistent and a fresh start would help
- The user deployed code changes and wants them applied

## When NOT to Restart

Do not restart:
- Mid-conversation without warning — always tell the user first
- For trivial changes that don't require it (persona switches via `/persona` work without restart)
- Repeatedly in a loop if something is broken — that won't fix the underlying issue
- Without saving context — the tool handles session persistence, but mention to the user what you were working on so they can resume

## How to Use

1. **Tell the user** what you're about to do and why
2. **Call `system_restart`** with a clear reason
3. The tool saves all sessions, then replaces the process
4. On restart, sessions rehydrate from disk automatically

Example:
```
User: "restart yourself"
Aki: "Restarting now — sessions are saved and will resume."
→ system_restart(reason="User requested restart")
```

## What Happens During Restart

- All active sessions are suspended to disk (.aki/sessions/)
- The process replaces itself via `os.execv` (same command, fresh state)
- Gateway mode: Discord reconnects automatically
- CLI mode: User needs to re-enter `aki chat`
- Memory is not lost — everything persists on disk
