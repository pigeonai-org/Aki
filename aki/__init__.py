"""
Aki — An agentic system with personality and autonomy.

A multi-agent platform where agents have persistent identity, memory, and the
autonomy to plan, delegate, and execute complex tasks through a ReAct loop.

Key Components:
- Agent System: ReAct loop with multi-agent orchestration and role-based delegation
- Personality: Persistent identity and communication style per agent
- Tools: 30+ executor tools (Audio, Vision, Translation, File I/O, Web, Memory)
- Models: Unified interface for OpenAI / Anthropic / Google / Qwen providers
- Memory: Short-term (per-task) and long-term (persistent Markdown) memory
- Skills: Markdown-based workflow definitions
- Gateway: Multi-platform messaging with persistence and context compaction
- MCP: Model Context Protocol server and client for tool interop
- API: REST API and CLI for interactive agent sessions
"""

__version__ = "0.1.0"
__author__ = "Pigeon.AI"

from aki.agent import UniversalAgent
from aki.config import Settings, get_settings
from aki.memory import MemoryManager, get_memory_manager
from aki.models import ModelConfig, ModelRegistry, ModelType
from aki.tools import BaseTool, ToolRegistry

__all__ = [
    # Version
    "__version__",
    "__author__",
    # Agent
    "UniversalAgent",
    # Tools
    "BaseTool",
    "ToolRegistry",
    # Models
    "ModelConfig",
    "ModelRegistry",
    "ModelType",
    # Memory
    "MemoryManager",
    "get_memory_manager",
    # Config
    "Settings",
    "get_settings",
]
