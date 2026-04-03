"""
MCP Server Adapter

Exposes Aki capabilities as an MCP server.
Allows Claude, Cursor, and other MCP clients to use Aki tools.
"""

from typing import Any, Optional

from aki.agent import AgentOrchestrator, OrchestratorConfig
from aki.config import get_settings
from aki.models import ModelConfig, ModelRegistry, ModelType
from aki.runtime import build_memory_manager


class MCPServerAdapter:
    """
    MCP Server Adapter.

    Wraps Aki functionality as MCP tools that can be called
    by MCP clients (Claude, Cursor, etc.).
    """

    def __init__(self, orchestrator: Optional[AgentOrchestrator] = None):
        """
        Initialize the MCP server adapter.

        Args:
            orchestrator: Agent orchestrator (uses global if not provided)
        """
        self.orchestrator = orchestrator or self._build_default_orchestrator()
        self._tools: dict[str, dict[str, Any]] = {}
        self._register_default_tools()

    @staticmethod
    def _resolve_api_key(provider: str) -> Optional[str]:
        settings = get_settings()
        if provider == "openai":
            return settings.openai_api_key
        if provider == "anthropic":
            return settings.anthropic_api_key
        if provider == "google":
            return settings.google_api_key
        if provider == "qwen":
            return settings.dashscope_api_key
        return None

    @classmethod
    def _build_default_orchestrator(cls) -> AgentOrchestrator:
        settings = get_settings()
        llm_config = ModelConfig.from_string(settings.default_llm)
        llm_config.api_key = cls._resolve_api_key(llm_config.provider)
        if llm_config.provider == "openai" and settings.openai_base_url:
            llm_config.base_url = settings.openai_base_url

        llm = ModelRegistry.get(llm_config, ModelType.LLM)
        memory = build_memory_manager(settings)
        config = OrchestratorConfig(
            max_agents_per_task=settings.agent.max_agents_per_task,
            max_agent_depth=settings.agent.max_agent_depth,
        )
        return AgentOrchestrator(config=config, llm=llm, memory=memory)

    def _register_default_tools(self) -> None:
        """Register default Aki tools for MCP."""
        self._tools["subtitle_generate"] = {
            "name": "subtitle_generate",
            "description": "Generate subtitles for a video file with translation",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "video_path": {
                        "type": "string",
                        "description": "Path to the video file",
                    },
                    "source_language": {
                        "type": "string",
                        "description": "Source language code (e.g., 'en')",
                    },
                    "target_language": {
                        "type": "string",
                        "description": "Target language code (e.g., 'zh')",
                    },
                    "enable_vision": {
                        "type": "boolean",
                        "description": "Enable vision analysis for context",
                        "default": False,
                    },
                },
                "required": ["video_path"],
            },
        }

        self._tools["video_analyze"] = {
            "name": "video_analyze",
            "description": "Analyze a video for content understanding",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "video_path": {
                        "type": "string",
                        "description": "Path to the video file",
                    },
                    "analysis_type": {
                        "type": "string",
                        "enum": ["content", "transcript", "summary"],
                        "description": "Type of analysis to perform",
                    },
                },
                "required": ["video_path"],
            },
        }

        self._tools["translate_text"] = {
            "name": "translate_text",
            "description": "Translate text from one language to another",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to translate",
                    },
                    "source_language": {
                        "type": "string",
                        "description": "Source language code",
                    },
                    "target_language": {
                        "type": "string",
                        "description": "Target language code",
                    },
                },
                "required": ["text", "target_language"],
            },
        }

    def get_tools(self) -> list[dict[str, Any]]:
        """
        Get all available MCP tools.

        Returns:
            List of tool definitions in MCP format
        """
        return list(self._tools.values())

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Call an MCP tool.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result
        """
        if name not in self._tools:
            return {
                "error": f"Tool '{name}' not found",
                "available_tools": list(self._tools.keys()),
            }

        # Dispatch to appropriate handler
        if name == "subtitle_generate":
            return await self._handle_subtitle_generate(arguments)
        elif name == "video_analyze":
            return await self._handle_video_analyze(arguments)
        elif name == "translate_text":
            return await self._handle_translate_text(arguments)
        else:
            return {"error": f"Handler not implemented for tool: {name}"}

    async def _handle_subtitle_generate(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle subtitle generation request."""
        video_path = arguments.get("video_path")
        source_lang = arguments.get("source_language", "en")
        target_lang = arguments.get("target_language", "zh")
        enable_vision = arguments.get("enable_vision", False)

        task = f"""Generate subtitles for video: {video_path}
Source language: {source_lang}
Target language: {target_lang}
Enable vision: {enable_vision}"""

        try:
            result = await self.orchestrator.run_task(task, agent_type="main")
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_video_analyze(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle video analysis request."""
        video_path = arguments.get("video_path")
        analysis_type = arguments.get("analysis_type", "content")

        task = f"Analyze video: {video_path} - Type: {analysis_type}"

        try:
            result = await self.orchestrator.run_task(task, agent_type="main")
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_translate_text(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle text translation request."""
        text = arguments.get("text", "")
        source_lang = arguments.get("source_language", "auto")
        target_lang = arguments.get("target_language")

        task = f"""Translate the following text:
From: {source_lang}
To: {target_lang}
Text: {text}"""

        try:
            result = await self.orchestrator.run_task(task, agent_type="main")
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


def create_mcp_server() -> MCPServerAdapter:
    """Create an MCP server adapter instance."""
    return MCPServerAdapter()
