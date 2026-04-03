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
from aki.tools.personality import PersonalityListTool, PersonalitySelectTool  # noqa: F401

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
]
