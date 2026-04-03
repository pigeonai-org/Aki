"""
Permission Rules and Modes

Defines permission modes for agents and glob-based permission rules for tools.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PermissionMode(str, Enum):
    """Agent permission mode controlling tool access behavior."""

    DEFAULT = "default"  # Ask for dangerous ops, allow safe ops
    BYPASS = "bypass"  # Auto-allow everything (trusted context only)
    AUTO = "auto"  # Auto-allow safe, ask for dangerous
    PLAN = "plan"  # Show plan before executing
    STRICT = "strict"  # Ask for everything


class PermissionRule(BaseModel):
    """
    A single permission rule matching tools by glob pattern.

    Examples:
        PermissionRule(tool_pattern="file_write", action="ask")
        PermissionRule(tool_pattern="web_*", action="allow")
        PermissionRule(tool_pattern="*", action="deny")
    """

    tool_pattern: str = Field(..., description="Glob pattern matching tool names")
    action: str = Field(..., description="Action: 'allow', 'deny', or 'ask'")
    reason: str = Field(default="", description="Human-readable reason for this rule")

    def model_post_init(self, __context: Any) -> None:
        if self.action not in ("allow", "deny", "ask"):
            raise ValueError(f"Invalid action '{self.action}'. Must be 'allow', 'deny', or 'ask'.")
