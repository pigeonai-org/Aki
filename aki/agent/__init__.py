"""
Agent module — multi-agent system with native tool calling.

Agents use Personality for identity/behavior and have full tool access.
"""

from aki.agent.base import (
    AgentError,
    AgentLimitExceeded,
    DepthLimitExceeded,
    UniversalAgent,
)
from aki.agent.logger import (
    AgentLogger,
    get_agent_logger,
    reset_agent_logger,
    set_verbose,
)
from aki.agent.orchestrator import (
    AgentOrchestrator,
    OrchestratorConfig,
    get_orchestrator,
    reset_orchestrator,
)
from aki.agent.state import AgentContext

__all__ = [
    # Base
    "UniversalAgent",
    # State
    "AgentContext",
    # Orchestrator
    "AgentOrchestrator",
    "OrchestratorConfig",
    "get_orchestrator",
    "reset_orchestrator",
    # Logger
    "AgentLogger",
    "get_agent_logger",
    "reset_agent_logger",
    "set_verbose",
    # Errors
    "AgentError",
    "DepthLimitExceeded",
    "AgentLimitExceeded",
]
