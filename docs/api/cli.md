# `aki.cli` API 文档

> 命令行界面 — Typer CLI 入口

---

## `aki.cli.main`

**文件路径：** `aki/cli/main.py`

Aki CLI Entry Point

Command-line interface for Aki operations.
---

#### `def resolve_quality_profile(profile: str) -> str` <small>(L366)</small>


---

#### `def profile_defaults(profile: str) -> dict[str, Any]` <small>(L370)</small>


---

#### `def version() -> None` <small>(L655)</small>

Show the Aki version.


---

#### `def config() -> None` <small>(L661)</small>

Show current configuration.


---

#### `def run(task: str = ..., agent: str = ..., verbose: bool = ...) -> None` <small>(L697)</small>

Run a task with the Aki agent system.


---

#### `def chat(role: str = ..., llm: str = ..., mcp: str = ..., verbose: bool = ...) -> None` <small>(L793)</small>

Start an interactive multi-turn chat session.


---

#### `def gateway(discord_token: str = ..., discord_channels: str = ..., host: str = ..., port: int = ...) -> None` <small>(L924)</small>

Start the gateway (Discord bot + REST API in one process).


---

#### `def subtitle(video: str = ..., source_lang: str = ..., target_lang: str = ..., output: Optional[str] = ..., enable_vision: bool = ..., quality: str = ..., verbose: bool = ...) -> None` <small>(L964)</small>

Generate subtitles for a video file.


---

#### `def translate(text: str = ..., target_lang: str = ..., source_lang: str = ...) -> None` <small>(L1024)</small>

Translate text using the translation agent.


---

#### `def tools() -> None` <small>(L1044)</small>

List all available tools.


---

#### `def agents() -> None` <small>(L1077)</small>

List all available agents.


---

#### `def memory_stats() -> None` <small>(L1099)</small>

Show memory statistics.


---

#### `def memory_list(query: Optional[str] = ..., limit: int = ..., categories: Optional[str] = ..., namespace: Optional[str] = ..., include_expired: bool = ...) -> None` <small>(L1109)</small>

List long-term memory records.


---

#### `def memory_prune() -> None` <small>(L1150)</small>

Prune expired long-term memory records.


---

#### `def memory_upsert_instruction(key: str = ..., content: str = ..., namespace: Optional[str] = ..., source_uri: Optional[str] = ...) -> None` <small>(L1158)</small>

Upsert a user instruction into long-term memory.


---

#### `def memory_migrate_legacy_json(source_file: str = ..., namespace: Optional[str] = ..., dry_run: bool = ...) -> None` <small>(L1181)</small>

Migrate a legacy JSON memory file into long-term memory.


---

#### `def serve(host: str = ..., port: int = ...) -> None` <small>(L1204)</small>

Run Aki as an HTTP API server for interactive agent sessions.


---

#### `def mcp_server() -> None` <small>(L1218)</small>

Run Aki as an MCP server (stdio transport).


---

#### `def mcp_status() -> None` <small>(L1238)</small>

Check MCP SDK installation status.


---

#### `def mcp_call(url: str = ..., tool: str = ..., args: str = ..., server_name: str = ...) -> None` <small>(L1260)</small>

Call tools on a remote MCP server (streamable HTTP).

Examples:

    # List available tools
    aki mcp-call -u http://localhost:8001/mcp

    # Call a specific tool
    aki mcp-call -u http://localhost:8001/mcp -t get_recommendations -a '{"user_id":"abc","limit":5}'


---

#### `def main() -> None` <small>(L1328)</small>

Aki - A Multi-Agent Video Subtitle Generation System.



---

