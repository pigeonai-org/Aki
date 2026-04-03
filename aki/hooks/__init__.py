"""
Hook and Permission System

Lifecycle hooks for agent tool execution, session management, and permission control.
"""

from aki.hooks.engine import HookEngine
from aki.hooks.permission import PermissionEngine
from aki.hooks.rules import PermissionMode, PermissionRule
from aki.hooks.types import EventType, HookEvent, HookResult

__all__ = [
    "EventType",
    "HookEngine",
    "HookEvent",
    "HookResult",
    "PermissionEngine",
    "PermissionMode",
    "PermissionRule",
]
