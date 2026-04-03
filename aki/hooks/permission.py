"""
Permission Engine

Evaluates tool permission against an agent's permission mode and rules.
Integrates with HookEngine for PERMISSION_REQUEST events.
"""

import fnmatch
import logging
from typing import Any

from aki.hooks.engine import HookEngine
from aki.hooks.rules import PermissionMode, PermissionRule
from aki.hooks.types import EventType, HookEvent, HookResult

logger = logging.getLogger(__name__)


class PermissionEngine:
    """
    Evaluates whether a tool call is permitted given a mode and a rule set.

    Decision flow:
    1. BYPASS mode -> always allow
    2. STRICT mode -> always fire PERMISSION_REQUEST hook
    3. Check deny rules -> if matched, deny
    4. Check allow rules -> if matched, allow
    5. Check ask rules -> if matched, fire PERMISSION_REQUEST hook
    6. DEFAULT mode -> allow (no matching rule = safe)
    7. AUTO mode -> allow (rely on external classifier hook if registered)
    """

    def __init__(self, hook_engine: HookEngine) -> None:
        self._hook_engine = hook_engine

    async def check_permission(
        self,
        agent_id: str,
        tool_name: str,
        tool_params: dict[str, Any],
        mode: PermissionMode,
        rules: list[PermissionRule],
    ) -> bool:
        """
        Evaluate whether a tool call is permitted.

        Args:
            agent_id: The calling agent's ID.
            tool_name: Name of the tool being invoked.
            tool_params: Parameters passed to the tool.
            mode: The agent's current permission mode.
            rules: Ordered list of permission rules.

        Returns:
            True if the call is permitted, False otherwise.
        """
        # Fast path: bypass allows everything
        if mode == PermissionMode.BYPASS:
            return True

        # Strict mode: always ask
        if mode == PermissionMode.STRICT:
            return await self._request_permission(agent_id, tool_name, tool_params)

        # Evaluate rules in order (first match wins)
        for rule in rules:
            if fnmatch.fnmatch(tool_name, rule.tool_pattern):
                if rule.action == "deny":
                    logger.info("Tool '%s' denied by rule: %s", tool_name, rule.reason or rule.tool_pattern)
                    return False
                if rule.action == "allow":
                    return True
                if rule.action == "ask":
                    return await self._request_permission(agent_id, tool_name, tool_params)

        # No matching rule: default behavior
        if mode in (PermissionMode.DEFAULT, PermissionMode.AUTO):
            return True

        # PLAN mode: deny by default (plan must be approved first)
        if mode == PermissionMode.PLAN:
            return False

        raise ValueError(f"Unknown permission mode: {mode}")

    async def _request_permission(
        self,
        agent_id: str,
        tool_name: str,
        tool_params: dict[str, Any],
    ) -> bool:
        """
        Fire a PERMISSION_REQUEST hook and return the decision.

        If no handler is registered, defaults to allow (to avoid blocking in
        non-interactive contexts).
        """
        if not self._hook_engine.has_handlers(EventType.PERMISSION_REQUEST):
            # No permission handler registered -> deny in STRICT mode, allow otherwise
            return False

        event = HookEvent(
            event_type=EventType.PERMISSION_REQUEST,
            agent_id=agent_id,
            data={
                "tool_name": tool_name,
                "tool_params": tool_params,
            },
        )
        result: HookResult = await self._hook_engine.fire(event)
        return result.allow
