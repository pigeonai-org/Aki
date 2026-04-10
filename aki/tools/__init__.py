"""
Tools module - Pure executor tools.

Tools are stateless, deterministic functions that perform specific tasks.
They have no thinking capability and cannot call other tools or spawn agents.
"""

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry

# Import tools to register them
from aki.tools.audio import AudioExtractTool, AudioVADTool, TranscribeTool  # noqa: F401
from aki.tools.io import (  # noqa: F401
    FileListTool,
    FileReadTool,
    FileWriteTool,
    SRTReadTool,
    SRTWriteTool,
)
from aki.tools.subtitle import (  # noqa: F401
    SubtitleEditTool,
    SubtitleProofreadTool,
    SubtitleTranslateTool,
)
from aki.tools.text import ProofreadTool, TranslateTool  # noqa: F401
from aki.tools.vision import VisionAnalyzeTool, VideoFrameExtractTool  # noqa: F401
from aki.tools.read_skill import ReadSkillTool  # noqa: F401
from aki.tools.skills_search import SkillsSearchTool  # noqa: F401
from aki.tools.delegate_to_worker import DelegateToWorkerTool  # noqa: F401
from aki.tools.memory import MemoryListTool, MemoryReadTool, MemoryWriteTool  # noqa: F401
from aki.tools.personality import PersonalityListTool, PersonalitySelectTool, PersonalityInfoTool  # noqa: F401
from aki.tools.system import SystemRestartTool, ShellTool  # noqa: F401
from aki.tools.opencli import OpenCLITool  # noqa: F401
from aki.tools.io.web import TavilySearchTool, WebPageReadTool  # noqa: F401
from aki.tools.io.pdf import PDFReadTool  # noqa: F401
from aki.tools.agent.check_task import CheckAgentTaskTool  # noqa: F401
from aki.tools.agent.send_message import SendAgentMessageTool  # noqa: F401
from aki.tools.agent.read_shared import ReadSharedStateTool  # noqa: F401
from aki.tools.agent.write_shared import WriteSharedStateTool  # noqa: F401

__all__ = [
    "BaseTool",
    "ToolParameter",
    "ToolResult",
    "ToolRegistry",
    # Audio tools
    "AudioExtractTool",
    "AudioVADTool",
    "TranscribeTool",
    # Vision tools
    "VisionAnalyzeTool",
    "VideoFrameExtractTool",
    # Text tools
    "TranslateTool",
    "ProofreadTool",
    # IO tools
    "FileReadTool",
    "FileWriteTool",
    "FileListTool",
    "SRTReadTool",
    "SRTWriteTool",
    # Subtitle tools
    "SubtitleTranslateTool",
    "SubtitleProofreadTool",
    "SubtitleEditTool",
    # Orchestrator tools
    "SkillsSearchTool",
    "ReadSkillTool",
    "DelegateToWorkerTool",
    # Memory tools
    "MemoryListTool",
    "MemoryReadTool",
    "MemoryWriteTool",
    # Personality tools
    "PersonalityListTool",
    "PersonalitySelectTool",
    "PersonalityInfoTool",
    # System tools
    "SystemRestartTool",
    "ShellTool",
    # OpenCLI tools
    "OpenCLITool",
    # Web tools
    "TavilySearchTool",
    "WebPageReadTool",
    "PDFReadTool",
    # Agent communication tools
    "CheckAgentTaskTool",
    "SendAgentMessageTool",
    "ReadSharedStateTool",
    "WriteSharedStateTool",
]
