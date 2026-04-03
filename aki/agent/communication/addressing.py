"""
Agent Addressing

Parses and resolves pipeline-style agent addresses.
Format: [project:]role[:instance]
"""

import fnmatch
from typing import Optional


class AgentAddress:
    """
    Parses and resolves pipeline-style agent addresses.

    Address format: ``[project:]role[:instance]``

    Examples:
        - ``"Localizer"`` — matches any Localizer agent
        - ``"translation:Localizer"`` — matches Localizer in the "translation" project
        - ``"task_abc:MediaExtractor:0"`` — matches specific instance 0
    """

    __slots__ = ("project", "role", "instance")

    def __init__(self, project: Optional[str], role: str, instance: Optional[str]) -> None:
        self.project = project
        self.role = role
        self.instance = instance

    @classmethod
    def parse(cls, address: str) -> "AgentAddress":
        """
        Parse an address string into components.

        Args:
            address: Address string like "project:role:instance", "role:instance", or "role".

        Returns:
            AgentAddress with parsed components.
        """
        parts = address.split(":")
        if len(parts) == 3:
            return cls(project=parts[0], role=parts[1], instance=parts[2])
        elif len(parts) == 2:
            return cls(project=parts[0], role=parts[1], instance=None)
        else:
            return cls(project=None, role=parts[0], instance=None)

    def matches(self, pattern: str) -> bool:
        """
        Check if this address matches a pattern.

        Pattern components use glob matching. Missing components in the
        pattern are treated as wildcards.

        Args:
            pattern: Address pattern to match against.

        Returns:
            True if this address matches the pattern.
        """
        pat = AgentAddress.parse(pattern)

        # Check project
        if pat.project is not None and self.project is not None:
            if not fnmatch.fnmatch(self.project, pat.project):
                return False
        elif pat.project is not None and self.project is None:
            return False

        # Check role (always required)
        if not fnmatch.fnmatch(self.role, pat.role):
            return False

        # Check instance
        if pat.instance is not None and self.instance is not None:
            if not fnmatch.fnmatch(self.instance, pat.instance):
                return False
        elif pat.instance is not None and self.instance is None:
            return False

        return True

    def __str__(self) -> str:
        parts = []
        if self.project:
            parts.append(self.project)
        parts.append(self.role)
        if self.instance:
            parts.append(self.instance)
        return ":".join(parts)

    def __repr__(self) -> str:
        return f"AgentAddress({self})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AgentAddress):
            return False
        return self.project == other.project and self.role == other.role and self.instance == other.instance

    def __hash__(self) -> int:
        return hash((self.project, self.role, self.instance))
