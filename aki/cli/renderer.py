"""
CLI Renderer — Claude Code-style terminal UI.

Renders agent activity inline with minimal chrome:
- User input shown with dimmed prompt
- Agent replies rendered as markdown
- Tool calls shown as collapsible one-liners
- Thinking state shown with animated spinner
- Errors shown inline in red
"""

import sys
import time
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from aki.cli.events import UIEvent, UIEventBus, UIEventSubscriber, UIEventType


_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class AgentStatus:
    """Tracks the current state of a single agent for rendering."""

    __slots__ = ("agent_id", "name", "status", "start_time", "is_focus")

    def __init__(self, agent_id: str, name: str = "", is_focus: bool = False) -> None:
        self.agent_id = agent_id
        self.name = name or agent_id[:8]
        self.status = "idle"
        self.start_time = time.monotonic()
        self.is_focus = is_focus


class RichRenderer:
    """Claude Code-style inline renderer.

    Prints events as they happen — no Rich.Live, no panels by default.
    Clean, minimal output that stays out of the way.
    """

    def __init__(self, event_bus: UIEventBus, console: Console) -> None:
        self._bus = event_bus
        self._sub: UIEventSubscriber = event_bus.subscribe()
        self._console = console
        self._agents: dict[str, AgentStatus] = {}
        self._watch_target: str | None = None
        self._running = True
        self._last_spinner_line: bool = False  # track if we need to clear spinner

    async def run(self) -> None:
        """Main render loop — consumes events and prints output."""
        while self._running:
            event = await self._sub.next(timeout=0.25)
            if event is not None:
                self._handle(event)

    def _handle(self, event: UIEvent) -> None:
        eid = event.agent_id

        if event.type == UIEventType.AGENT_THINKING:
            agent = self._ensure_agent(eid)
            agent.status = "thinking"
            agent.start_time = time.monotonic()
            iteration = event.data.get("iteration", 0)
            if self._should_show(eid):
                self._clear_spinner()
                frame = _SPINNER_FRAMES[iteration % len(_SPINNER_FRAMES)]
                elapsed = time.monotonic() - agent.start_time
                label = f"  {frame} Thinking..."
                if iteration > 1:
                    label += f" (step {iteration})"
                sys.stdout.write(f"\r\033[K\033[2m{label}\033[0m")
                sys.stdout.flush()
                self._last_spinner_line = True

        elif event.type == UIEventType.TOOL_START:
            agent = self._ensure_agent(eid)
            tool_name = event.data.get("tool_name", "?")

            # Handle agent spawn
            if tool_name == "__agent_spawn__":
                params = event.data.get("params", {})
                role_name = params.get("role_name", "Worker")
                spawned = self._ensure_agent(eid, name=role_name)
                spawned.status = "thinking"
                self._clear_spinner()
                self._console.print(f"  [dim]+ {role_name}[/dim]")
                return

            agent.status = f"tool:{tool_name}"
            agent.start_time = time.monotonic()
            if self._should_show(eid):
                self._clear_spinner()
                params = event.data.get("params", {})
                params_str = _format_tool_params(params)
                self._console.print(
                    f"  [dim cyan]{tool_name}[/dim cyan][dim]({params_str})[/dim]",
                    highlight=False,
                )

        elif event.type == UIEventType.TOOL_END:
            agent = self._ensure_agent(eid)
            tool_name = event.data.get("tool_name", "?")
            success = event.data.get("success", True)
            duration = event.data.get("duration_ms", 0)
            agent.status = "thinking"
            if self._should_show(eid):
                marker = "[green]✓[/green]" if success else "[red]✗[/red]"
                dur_str = f" {duration:.0f}ms" if duration else ""
                self._console.print(
                    f"  {marker} [dim]{tool_name}{dur_str}[/dim]",
                    highlight=False,
                )

        elif event.type == UIEventType.AGENT_REPLY:
            agent = self._ensure_agent(eid)
            agent.status = "idle"
            content = event.data.get("content", "")
            self._clear_spinner()
            if content:
                # Render as markdown for rich formatting
                self._console.print()
                try:
                    md = Markdown(content)
                    self._console.print(md)
                except Exception:
                    self._console.print(content)
                self._console.print()

        elif event.type == UIEventType.AGENT_SPAWN:
            agent_id = event.data.get("agent_id", eid)
            name = event.data.get("role_name", "Worker")
            agent = self._ensure_agent(agent_id, name=name)
            agent.status = "thinking"
            self._clear_spinner()
            self._console.print(f"  [dim]+ Background: {name}[/dim]")

        elif event.type == UIEventType.AGENT_COMPLETE:
            agent = self._ensure_agent(eid)
            agent.status = "completed"
            # Silent — don't clutter output for normal completions

        elif event.type == UIEventType.BTW_REPLY:
            reply = event.data.get("reply", "")
            self._clear_spinner()
            self._console.print(f"\n[dim italic]btw:[/dim italic] {reply}\n")

        elif event.type == UIEventType.ERROR:
            error = event.data.get("error", "Unknown error")
            self._clear_spinner()
            self._console.print(f"\n[bold red]Error:[/bold red] {error}\n")

    def _clear_spinner(self) -> None:
        """Clear the spinner line if one was written."""
        if self._last_spinner_line:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
            self._last_spinner_line = False

    # ── Agent tracking ──

    def _ensure_agent(self, agent_id: str, name: str = "") -> AgentStatus:
        if agent_id not in self._agents:
            self._agents[agent_id] = AgentStatus(agent_id, name=name)
        elif name:
            self._agents[agent_id].name = name
        return self._agents[agent_id]

    def sync_from_task_registry(self, task_registry: object) -> None:
        if not hasattr(task_registry, "list_all"):
            return
        for task in task_registry.list_all():
            agent = self._ensure_agent(task.agent_id, name=task.role_name)
            status_map = {
                "running": "thinking",
                "completed": "completed",
                "failed": "failed",
                "cancelled": "failed",
                "pending": "idle",
            }
            agent.status = status_map.get(task.status.value, task.status.value)

    def show_agent_panel(self) -> None:
        if not self._agents:
            self._console.print("[dim]No active agents.[/dim]")
            return

        table = Table(show_header=True, header_style="bold dim", box=None, padding=(0, 2))
        table.add_column("", width=1)
        table.add_column("Agent", style="cyan")
        table.add_column("Status")
        table.add_column("Time", justify="right", style="dim")

        for agent in self._agents.values():
            icon = "●" if agent.is_focus else "○"
            elapsed = f"{time.monotonic() - agent.start_time:.0f}s"
            if agent.status.startswith("tool:"):
                status_text = f"[yellow]{agent.status[5:]}[/yellow]"
            elif agent.status == "thinking":
                status_text = "[blue]thinking[/blue]"
            elif agent.status == "completed":
                status_text = "[green]done[/green]"
            elif agent.status == "failed":
                status_text = "[red]failed[/red]"
            else:
                status_text = "[dim]idle[/dim]"
            table.add_row(icon, agent.name, status_text, elapsed)

        self._console.print(table)

    # ── Watch / Focus ──

    def set_watch(self, agent_id: str | None) -> None:
        self._watch_target = agent_id

    def set_focus(self, agent_id: str) -> None:
        for a in self._agents.values():
            a.is_focus = (a.agent_id == agent_id)

    def _should_show(self, agent_id: str) -> bool:
        if self._watch_target is not None:
            return agent_id == self._watch_target
        return True

    def stop(self) -> None:
        self._clear_spinner()
        self._running = False


def _format_tool_params(params: dict[str, Any], max_len: int = 60) -> str:
    """Format tool params as a compact one-liner."""
    if not params:
        return ""
    parts = []
    for k, v in params.items():
        v_str = str(v)
        if len(v_str) > 30:
            v_str = v_str[:27] + "..."
        parts.append(f"{k}={v_str}")
    result = ", ".join(parts)
    if len(result) > max_len:
        result = result[:max_len - 3] + "..."
    return result
