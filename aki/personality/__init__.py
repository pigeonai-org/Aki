"""Aki personality system — persistent identity and communication style."""

from aki.personality.registry import (
    Personality,
    discover_personalities,
    get_personality,
    load_personality,
)

__all__ = [
    "Personality",
    "discover_personalities",
    "get_personality",
    "load_personality",
]
