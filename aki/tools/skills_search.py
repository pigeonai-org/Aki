"""Tool for discovering and ranking available skills."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from aki.skills.registry import get_skills_metadata
from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry


def _normalize_text(value: str) -> str:
    """Normalize a free-form string for token matching."""
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _tokenize(value: str) -> set[str]:
    """Split normalized text into unique tokens."""
    normalized = _normalize_text(value)
    if not normalized:
        return set()
    return {token for token in normalized.split(" ") if token}


def _skill_match_score(query: str, name: str, description: str) -> float:
    """Compute a deterministic relevance score for one skill candidate."""
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return 0.0

    normalized_name = _normalize_text(name)
    normalized_description = _normalize_text(description)
    searchable = f"{normalized_name} {normalized_description}".strip()

    query_tokens = _tokenize(normalized_query)
    skill_tokens = _tokenize(searchable)
    token_overlap = (
        len(query_tokens & skill_tokens) / len(query_tokens) if query_tokens else 0.0
    )

    name_substring = 1.0 if normalized_query and normalized_query in normalized_name else 0.0
    description_substring = (
        1.0 if normalized_query and normalized_query in normalized_description else 0.0
    )
    fuzzy_name = (
        SequenceMatcher(None, normalized_query, normalized_name).ratio()
        if normalized_name
        else 0.0
    )
    fuzzy_combined = (
        SequenceMatcher(None, normalized_query, searchable).ratio() if searchable else 0.0
    )

    return (
        token_overlap * 0.45
        + name_substring * 0.25
        + description_substring * 0.1
        + fuzzy_name * 0.15
        + fuzzy_combined * 0.05
    )


@ToolRegistry.register
class SkillsSearchTool(BaseTool):
    """List skills and return query-ranked skill matches."""

    name = "skills_search"
    description = "Search available skills and return ranked matches for a task query."
    parameters = [
        ToolParameter(
            name="query",
            type="string",
            description="Optional natural-language task query used to rank skills.",
            required=False,
            default="",
        ),
        ToolParameter(
            name="limit",
            type="integer",
            description="Maximum number of ranked matches to return.",
            required=False,
            default=5,
        ),
    ]
    concurrency_safe = True

    async def execute(
        self,
        query: str = "",
        limit: int = 5,
        **kwargs: Any,
    ) -> ToolResult:
        """Return available skills and optional ranked matches for the query."""
        del kwargs
        normalized_query = (query or "").strip()
        safe_limit = max(1, int(limit or 5))

        skills = sorted(
            get_skills_metadata(),
            key=lambda item: str(item.get("name", "")),
        )

        ranked_matches: list[dict[str, Any]] = []
        if normalized_query:
            scored: list[dict[str, Any]] = []
            for item in skills:
                name = str(item.get("name", "")).strip()
                description = str(item.get("description", "")).strip()
                score = _skill_match_score(normalized_query, name, description)
                if score > 0.0:
                    scored.append(
                        {
                            "name": name,
                            "description": description,
                            "score": round(score, 6),
                        }
                    )

            scored.sort(key=lambda item: (-float(item["score"]), str(item["name"])))
            ranked_matches = scored[:safe_limit]

        best_match = ranked_matches[0]["name"] if ranked_matches else None
        return ToolResult.ok(
            data={
                "query": normalized_query,
                "skills": skills,
                "matches": ranked_matches,
                "best_match": best_match,
            }
        )
