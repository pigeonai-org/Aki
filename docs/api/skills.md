# `aki.skills` API 文档

> 技能系统 — 技能注册表、Frontmatter 加载

---

## `aki.skills.registry`

**文件路径：** `aki/skills/registry.py`

Skill Registry Module

Handles parsing and loading Anthropic Skill markdown files.
Implements progressive disclosure by exposing only lightweight YAML frontmatter
to the orchestrator initially, loading the full text only on demand.
---

#### `def get_skills_base_dir() -> Path` <small>(L17)</small>

Return the absolute path to the skills directory.


---

#### `def load_skill_frontmatter(skill_name: str) -> dict[str, Any] | None` <small>(L52)</small>

Fetch parsed YAML frontmatter for a specific skill.


---

#### `def get_skills_metadata() -> list[dict[str, str]]` <small>(L60)</small>

Scan the skills directory and extract metadata from skill markdown frontmatter.


---

#### `def load_skill_body(skill_name: str) -> str | None` <small>(L88)</small>

Fetch the full Markdown text for a specific skill.



---

