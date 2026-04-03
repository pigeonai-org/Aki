"""
MCP Server Implementation

Real MCP server using the official MCP Python SDK.
Exposes Aki capabilities as an MCP server.
"""

import asyncio
from typing import Any

from aki.agent import AgentOrchestrator, OrchestratorConfig
from aki.config import get_settings
from aki.models import ModelConfig, ModelRegistry, ModelType
from aki.runtime import build_memory_manager

def _resolve_api_key_for_provider(provider: str) -> str | None:
    """Resolve provider-specific API key from settings."""
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


# Check if MCP is available
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    Server = None  # type: ignore


def create_mcp_server_instance() -> "Server | None":
    """
    Create a real MCP server instance.

    Returns:
        MCP Server instance, or None if MCP SDK not installed
    """
    if not MCP_AVAILABLE:
        return None

    server = Server("aki")

    # Store orchestrator reference
    _orchestrator: AgentOrchestrator | None = None

    def get_or_create_orchestrator() -> AgentOrchestrator:
        nonlocal _orchestrator
        if _orchestrator is None:
            settings = get_settings()
            llm_config = ModelConfig.from_string(settings.default_llm)
            llm_config.api_key = _resolve_api_key_for_provider(llm_config.provider)
            if llm_config.provider == "openai" and settings.openai_base_url:
                llm_config.base_url = settings.openai_base_url

            llm = ModelRegistry.get(llm_config, ModelType.LLM)
            memory = build_memory_manager(settings)
            orchestrator_config = OrchestratorConfig(
                max_agents_per_task=settings.agent.max_agents_per_task,
                max_agent_depth=settings.agent.max_agent_depth,
            )
            _orchestrator = AgentOrchestrator(
                config=orchestrator_config,
                llm=llm,
                memory=memory,
            )
        return _orchestrator

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List all available Aki tools."""
        return [
            Tool(
                name="subtitle_generate",
                description="Generate subtitles for a video file with optional translation",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "video_path": {
                            "type": "string",
                            "description": "Path to the video file",
                        },
                        "source_language": {
                            "type": "string",
                            "description": "Source language code (e.g., 'en', 'zh')",
                            "default": "en",
                        },
                        "target_language": {
                            "type": "string",
                            "description": "Target language code (e.g., 'zh', 'en')",
                            "default": "zh",
                        },
                        "enable_vision": {
                            "type": "boolean",
                            "description": "Enable vision analysis for better context",
                            "default": False,
                        },
                    },
                    "required": ["video_path"],
                },
            ),
            Tool(
                name="video_analyze",
                description="Analyze a video for content understanding",
                inputSchema={
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
                            "default": "content",
                        },
                    },
                    "required": ["video_path"],
                },
            ),
            Tool(
                name="translate_text",
                description="Translate text from one language to another",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text to translate",
                        },
                        "source_language": {
                            "type": "string",
                            "description": "Source language (or 'auto' for detection)",
                            "default": "auto",
                        },
                        "target_language": {
                            "type": "string",
                            "description": "Target language code",
                        },
                    },
                    "required": ["text", "target_language"],
                },
            ),
            Tool(
                name="transcribe_audio",
                description="Transcribe audio to text using speech recognition",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "audio_path": {
                            "type": "string",
                            "description": "Path to the audio file",
                        },
                        "language": {
                            "type": "string",
                            "description": "Language of the audio",
                        },
                    },
                    "required": ["audio_path"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool calls from MCP clients."""
        orchestrator = get_or_create_orchestrator()

        try:
            if name == "subtitle_generate":
                result = await _handle_subtitle_generate(orchestrator, arguments)
            elif name == "video_analyze":
                result = await _handle_video_analyze(orchestrator, arguments)
            elif name == "translate_text":
                result = await _handle_translate_text(orchestrator, arguments)
            elif name == "transcribe_audio":
                result = await _handle_transcribe_audio(orchestrator, arguments)
            else:
                result = f"Unknown tool: {name}"

            return [TextContent(type="text", text=str(result))]

        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    return server


async def _handle_subtitle_generate(
    orchestrator: AgentOrchestrator,
    arguments: dict[str, Any],
) -> str:
    """Handle subtitle generation."""
    video_path = arguments.get("video_path")
    source_lang = arguments.get("source_language", "en")
    target_lang = arguments.get("target_language", "zh")
    enable_vision = arguments.get("enable_vision", False)

    task = f"""Generate subtitles for video: {video_path}
Source language: {source_lang}
Target language: {target_lang}
Enable vision analysis: {enable_vision}"""

    result = await orchestrator.run_task(task, agent_type="main")
    return str(result)


async def _handle_video_analyze(
    orchestrator: AgentOrchestrator,
    arguments: dict[str, Any],
) -> str:
    """Handle video analysis."""
    video_path = arguments.get("video_path")
    analysis_type = arguments.get("analysis_type", "content")

    task = f"Analyze video: {video_path} - Analysis type: {analysis_type}"

    result = await orchestrator.run_task(task, agent_type="main")
    return str(result)


async def _handle_translate_text(
    orchestrator: AgentOrchestrator,
    arguments: dict[str, Any],
) -> str:
    """Handle text translation."""
    text = arguments.get("text", "")
    source_lang = arguments.get("source_language", "auto")
    target_lang = arguments.get("target_language")

    task = f"""Translate text from {source_lang} to {target_lang}:
{text}"""

    result = await orchestrator.run_task(task, agent_type="translation")
    return str(result)


async def _handle_transcribe_audio(
    orchestrator: AgentOrchestrator,
    arguments: dict[str, Any],
) -> str:
    """Handle audio transcription."""
    audio_path = arguments.get("audio_path")
    language = arguments.get("language")

    task = f"Transcribe audio file: {audio_path}"
    if language:
        task += f" (language: {language})"

    result = await orchestrator.run_task(task, agent_type="audio")
    return str(result)


async def run_mcp_server() -> None:
    """
    Run the MCP server using stdio transport.

    This is the main entry point for running Aki as an MCP server.
    """
    if not MCP_AVAILABLE:
        raise ImportError(
            "MCP SDK not installed. Install with: pip install mcp"
        )

    server = create_mcp_server_instance()
    if server is None:
        raise RuntimeError("Failed to create MCP server")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """Entry point for MCP server."""
    asyncio.run(run_mcp_server())


if __name__ == "__main__":
    main()
