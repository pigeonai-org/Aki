"""
Focus Manager

Tracks which agent the user is currently interacting with (focus)
and which agent they're observing (watch).
"""


class FocusManager:
    """Manages user's current focus and watch targets.

    - **focus**: The agent that receives the user's chat input.
    - **watch**: The agent whose detailed activity stream is displayed.

    Commands:
    - ``/focus <name>`` → switch chat target
    - ``/watch <name>`` → observe agent activity stream
    - ``/unwatch`` → return to panel view
    - ``/agents`` → list all agents
    """

    def __init__(self, default_focus: str = "orchestrator") -> None:
        self.current_focus: str = default_focus
        self.watch_target: str | None = None

    def switch_focus(self, agent_id: str) -> None:
        """Switch user input target to a different agent."""
        self.current_focus = agent_id

    def start_watch(self, agent_id: str) -> None:
        """Start watching a specific agent's activity stream."""
        self.watch_target = agent_id

    def stop_watch(self) -> None:
        """Stop watching and return to panel mode."""
        self.watch_target = None

    @property
    def is_watching(self) -> bool:
        return self.watch_target is not None
