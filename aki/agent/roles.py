"""
Deprecated — Roles have been replaced by the Personality system.

The Role concept previously defined persona, system_prompt, and allowed_tools
for agents. Personality now handles identity and behavior. All agents have
full tool access.

This module is kept for backward compatibility only.
"""

from pydantic import BaseModel, Field
from typing import Any


class Role(BaseModel):
    """Deprecated. Kept for backward compatibility."""
    name: str = Field(default="agent")
    persona: str = Field(default="")
    system_prompt: str = Field(default="")
    allowed_tools: list[str] = Field(default_factory=lambda: ["*"])

    @classmethod
    def from_definition(cls, defn: Any) -> "Role":
        return cls(
            name=getattr(defn, "name", "agent"),
            persona=getattr(defn, "persona", ""),
            system_prompt=getattr(defn, "system_prompt", ""),
            allowed_tools=list(getattr(defn, "allowed_tools", ["*"])),
        )
