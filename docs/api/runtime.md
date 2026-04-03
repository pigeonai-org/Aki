# `aki.runtime` API 文档

> 运行时 — 依赖注入

---

## `aki.runtime.dependencies`

**文件路径：** `aki/runtime/dependencies.py`

Runtime factory helpers for dependency wiring.
---

#### `def build_memory_manager(settings: Settings) -> MemoryManager` <small>(L22)</small>

Build a configured MemoryManager from application settings.

Long-term memory is handled by the Markdown-based memory tools
(memory_write / memory_read / memory_list) that agents call directly.
The MemoryManager only manages short-term working memory.



---

