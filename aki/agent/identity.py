"""
Agent Identity and Definition

Persistent agent identities loaded from markdown frontmatter files.
AgentDefinition is a superset of Role, enabling per-agent model, maxTurns,
permission mode, and workspace configuration.
"""

import logging
import os
import re
from datetime import datetime
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

from aki.hooks.rules import PermissionMode, PermissionRule

logger = logging.getLogger(__name__)


class AgentDefinition(BaseModel):
    """
    Complete agent definition, loadable from .aki/agents/<name>/agent.md frontmatter.

    Superset of the existing Role class:
    - name, persona, system_prompt, allowed_tools (same as Role)
    - model, max_turns, temperature, permission_mode, permission_rules (new)
    - soul (extended personality document)
    - tags (categorization)
    """

    name: str = Field(..., description="Unique agent identifier")
    agent_type: str = Field(default="worker", description="'orchestrator', 'worker', or 'specialist'")
    persona: str = Field(default="", description="High-level character description")
    system_prompt: str = Field(default="", description="Core instructions")
    allowed_tools: list[str] = Field(default_factory=list, description="Tool whitelist")
    model: Optional[str] = Field(default=None, description="Model override (e.g. 'anthropic:claude-sonnet-4-20250514')")
    max_turns: int = Field(default=20, description="Maximum LLM turns per task")
    temperature: float = Field(default=0.7, description="Sampling temperature")
    permission_mode: PermissionMode = Field(default=PermissionMode.DEFAULT)
    permission_rules: list[PermissionRule] = Field(default_factory=list)
    workspace_dir: Optional[str] = Field(default=None, description="Per-agent state directory")
    soul: Optional[str] = Field(default=None, description="Extended personality markdown")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")

    @classmethod
    def from_markdown(cls, filepath: str) -> "AgentDefinition":
        """
        Load an agent definition from a markdown file with YAML frontmatter.

        File format::

            ---
            name: MediaExtractor
            agent_type: specialist
            persona: "You are a Media Extractor..."
            allowed_tools: [audio_extract, audio_vad, transcribe]
            model: "qwen:qwen3-asr-flash"
            max_turns: 10
            ---
            (Optional markdown body used as extended system prompt / soul)

        Args:
            filepath: Path to the agent.md file.

        Returns:
            AgentDefinition parsed from the file.
        """
        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        frontmatter, body = _parse_frontmatter(content)
        if not frontmatter:
            raise ValueError(f"No YAML frontmatter found in {filepath}")

        # Parse permission_rules from dicts if present
        raw_rules = frontmatter.pop("permission_rules", [])
        rules = [PermissionRule(**r) if isinstance(r, dict) else r for r in raw_rules]

        definition = cls(**frontmatter, permission_rules=rules)

        # Use markdown body as soul / extended system prompt
        if body.strip():
            if definition.soul is None:
                definition.soul = body.strip()
            if not definition.system_prompt:
                definition.system_prompt = body.strip()

        return definition


class AgentIdentity(BaseModel):
    """
    Runtime identity of an active agent instance.

    Tracks session count and state directory for persistent agents.
    """

    agent_id: str = Field(..., description="Unique runtime instance ID")
    definition: AgentDefinition
    state_dir: str = Field(default="", description="Path to agent's state directory")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    session_count: int = Field(default=0)

    def increment_session(self) -> None:
        """Record a new session for this agent."""
        self.session_count += 1


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    Extract YAML frontmatter and body from a markdown string.

    Returns:
        (frontmatter_dict, body_text)
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
    if not match:
        return {}, content

    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        logger.warning("Failed to parse YAML frontmatter")
        return {}, content

    body = match.group(2)
    return frontmatter, body


def discover_agent_definitions(agents_dir: str) -> dict[str, AgentDefinition]:
    """
    Discover agent definitions from a directory.

    Scans ``agents_dir`` for subdirectories containing ``agent.md`` files.

    Args:
        agents_dir: Path to the agents directory (e.g. ".aki/agents").

    Returns:
        Dict mapping agent name to AgentDefinition.
    """
    definitions: dict[str, AgentDefinition] = {}

    if not os.path.isdir(agents_dir):
        return definitions

    for entry in os.listdir(agents_dir):
        agent_dir = os.path.join(agents_dir, entry)
        agent_file = os.path.join(agent_dir, "agent.md")
        if os.path.isfile(agent_file):
            try:
                defn = AgentDefinition.from_markdown(agent_file)
                definitions[defn.name] = defn
                logger.debug("Discovered agent definition: %s", defn.name)
            except Exception:
                logger.warning("Failed to load agent definition from %s", agent_file)

    return definitions
