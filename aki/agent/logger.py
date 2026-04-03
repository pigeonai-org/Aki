"""
Agent Logger

Provides formatted logging for agent tool calls and lifecycle events.
"""

from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel


class AgentLogger:
    """Logger for agent activities."""

    def __init__(self, verbose: bool = True, console: Optional[Console] = None):
        self.verbose = verbose
        self.console = console or Console()
        self._indent_level = 0

    def set_verbose(self, verbose: bool) -> None:
        self.verbose = verbose

    def indent(self) -> None:
        self._indent_level += 1

    def dedent(self) -> None:
        self._indent_level = max(0, self._indent_level - 1)

    def _get_indent(self) -> str:
        return "  " * self._indent_level

    def agent_start(self, agent_name: str, task: str, depth: int) -> None:
        if not self.verbose:
            return
        depth_indicator = "🔵" if depth == 0 else "🟢" * depth
        self.console.print(
            Panel(
                f"[bold]{task}[/bold]",
                title=f"{depth_indicator} {agent_name.upper()} Agent (depth={depth})",
                border_style="blue" if depth == 0 else "green",
                padding=(0, 1),
            )
        )

    def agent_end(self, agent_name: str, result: Any) -> None:
        if not self.verbose:
            return
        indent = self._get_indent()
        result_str = str(result)
        if len(result_str) > 200:
            result_str = result_str[:200] + "..."
        self.console.print(f"{indent}[bold green]✓[/bold green] [{agent_name}] Completed: {result_str}\n")

    def tool_calls(self, _agent_name: str, calls: list[Any]) -> None:
        if not self.verbose:
            return
        indent = self._get_indent()
        for call in calls:
            name = getattr(call, "name", str(call))
            params = getattr(call, "input", {})
            params_str = str(params)
            if len(params_str) > 150:
                params_str = params_str[:150] + "..."
            self.console.print(f"{indent}  🔧 [cyan]{name}[/cyan] {params_str}")

    def error(self, agent_name: str, error: str) -> None:
        indent = self._get_indent()
        self.console.print(f"{indent}[red]✗ [{agent_name}] Error: {error}[/red]")

    def separator(self) -> None:
        if not self.verbose:
            return
        self.console.print()


# Global logger instance
_logger: Optional[AgentLogger] = None


def get_agent_logger() -> AgentLogger:
    global _logger
    if _logger is None:
        _logger = AgentLogger(verbose=False)
    return _logger


def set_verbose(verbose: bool) -> None:
    get_agent_logger().set_verbose(verbose)


def reset_agent_logger() -> None:
    global _logger
    _logger = None
