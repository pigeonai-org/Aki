"""
Tool for Orchestrator to read full skill files dynamically.
"""

from difflib import get_close_matches
from typing import Any

from aki.skills.registry import get_skills_metadata, load_skill_body
from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry


@ToolRegistry.register
class ReadSkillTool(BaseTool):
    """
    Tool to fetch the full markdown body of a skill.

    This fulfills the Progress Disclosure mechanism where the Orchestrator
    only sees metadata initially, and loads the full instructions when needed.
    """

    name: str = "read_skill"
    description: str = "Read the full markdown instructions for a specific skill workflow."
    parameters: list[ToolParameter] = [
        ToolParameter(
            name="skill_name",
            type="string",
            description="The exact name of the skill to read (e.g., 'subtitle-translation')",
            required=True,
        )
    ]
    concurrency_safe = True

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the skill read."""
        skill_name = kwargs.get("skill_name")

        if not skill_name:
            return ToolResult.fail("skill_name parameter is required.")

        normalized_skill_name = str(skill_name).strip()
        body = load_skill_body(normalized_skill_name)

        if body is None or body.startswith("Error loading"):
            skills_metadata = sorted(
                get_skills_metadata(),
                key=lambda item: str(item.get("name", "")),
            )
            available_names = [str(item.get("name", "")).strip() for item in skills_metadata]
            available_names = [name for name in available_names if name]
            suggestions = get_close_matches(normalized_skill_name, available_names, n=5, cutoff=0.2)
            error_message = (
                body
                or (
                    f"Skill '{normalized_skill_name}' not found. "
                    "Use skills_search first to discover available skills."
                )
            )
            return ToolResult.fail(
                error_message,
                requested_skill=normalized_skill_name,
                available_skills=skills_metadata,
                suggestions=suggestions,
                hint="Use skills_search first",
            )

        return ToolResult.ok(data={"skill_content": body})
