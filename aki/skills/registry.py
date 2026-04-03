"""
Skill Registry Module

Handles parsing and loading Anthropic Skill markdown files.
Implements progressive disclosure by exposing only lightweight YAML frontmatter
to the orchestrator initially, loading the full text only on demand.
"""

from pathlib import Path
from typing import Any

import yaml

SKILL_MD_CANDIDATES = ("Skill.md", "SKILL.md")


def get_skills_base_dir() -> Path:
    """Return the absolute path to the skills directory."""
    return Path(__file__).parent


def _resolve_skill_md_path(skill_dir: Path) -> Path | None:
    """Resolve the canonical markdown file for a skill directory."""
    for candidate_name in SKILL_MD_CANDIDATES:
        candidate = skill_dir / candidate_name
        if candidate.exists():
            return candidate
    return None


def _extract_frontmatter(markdown: str) -> dict[str, Any] | None:
    """Parse YAML frontmatter from markdown text."""
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    yaml_lines: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        yaml_lines.append(line)

    if not yaml_lines:
        return None

    parsed = yaml.safe_load("\n".join(yaml_lines))
    if isinstance(parsed, dict):
        return parsed
    return None


def load_skill_frontmatter(skill_name: str) -> dict[str, Any] | None:
    """Fetch parsed YAML frontmatter for a specific skill."""
    body = load_skill_body(skill_name)
    if body is None or body.startswith("Error loading"):
        return None
    return _extract_frontmatter(body)


def get_skills_metadata() -> list[dict[str, str]]:
    """Scan the skills directory and extract metadata from skill markdown frontmatter."""
    skills_dir = get_skills_base_dir()
    skills_metadata = []

    if not skills_dir.exists():
        return skills_metadata

    for item in skills_dir.iterdir():
        if item.is_dir():
            skill_md_path = _resolve_skill_md_path(item)
            if skill_md_path is not None:
                try:
                    with open(skill_md_path, encoding="utf-8") as f:
                        metadata = _extract_frontmatter(f.read())
                        if isinstance(metadata, dict) and "name" in metadata:
                            skills_metadata.append(
                                {
                                    "name": str(metadata.get("name")),
                                    "description": str(metadata.get("description", "")),
                                }
                            )
                except Exception as e:
                    print(f"Error parsing {skill_md_path}: {e}")

    return skills_metadata


def load_skill_body(skill_name: str) -> str | None:
    """Fetch the full Markdown text for a specific skill."""
    skills_dir = get_skills_base_dir()
    skill_dir = skills_dir / skill_name
    skill_md_path = _resolve_skill_md_path(skill_dir)

    if skill_md_path is not None:
        try:
            with open(skill_md_path, encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error loading skill body: {e}"

    return None
