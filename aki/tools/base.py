"""
Tool Base Classes

Tools are pure executors - they perform specific tasks without thinking or decision-making.
This is fundamentally different from Agents, which have ReAct loops.

Tool characteristics:
1. Deterministic: Same input produces same output
2. Stateless: No state preserved between calls
3. Single responsibility: Each tool does one thing
4. Cannot spawn agents or call other tools
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Optional

from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    """
    Tool parameter definition.

    Used to generate schema for MCP and OpenAI function calling.
    """

    name: str = Field(..., description="Parameter name")
    type: str = Field(
        ...,
        description="Parameter type (string, integer, boolean, array, object)",
    )
    description: str = Field(..., description="Parameter description")
    required: bool = Field(default=True, description="Whether the parameter is required")
    default: Any = Field(default=None, description="Default value")
    enum: Optional[list[Any]] = Field(default=None, description="Allowed values")


class ToolResult(BaseModel):
    """
    Unified tool execution result.

    All tool executions return this standardized result format.
    """

    success: bool = Field(..., description="Whether the execution succeeded")
    data: Any = Field(default=None, description="Result data")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (execution time, resource usage, etc.)",
    )

    @classmethod
    def ok(cls, data: Any, **metadata: Any) -> "ToolResult":
        """Create a successful result."""
        return cls(success=True, data=data, metadata=metadata)

    @classmethod
    def fail(cls, error: str, **metadata: Any) -> "ToolResult":
        """Create a failed result."""
        return cls(success=False, error=error, metadata=metadata)


class BaseTool(ABC):
    """
    Base class for all tools.

    Tools are pure executors with NO thinking capability.
    They cannot:
    - Access memory
    - Access knowledge base
    - Call other tools
    - Spawn agents
    - Make decisions

    Subclasses must implement:
    - execute(): The main execution logic
    """

    # Class attributes to be defined by subclasses
    name: str = ""  # Unique tool identifier
    description: str = ""  # Tool description for LLM understanding
    parameters: list[ToolParameter] = []  # Parameter definitions

    # Concurrency & streaming attributes (Phase 1)
    concurrency_safe: bool = False  # True if safe to run in parallel with other tools
    max_result_size: int = 50_000  # Results exceeding this (chars) are offloaded to disk

    def __init__(self) -> None:
        """Initialize the tool."""
        if not self.name:
            raise ValueError(f"{self.__class__.__name__} must define 'name' attribute")
        if not self.description:
            raise ValueError(f"{self.__class__.__name__} must define 'description' attribute")

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """
        Execute the tool.

        Subclasses must implement this method.

        IMPORTANT:
        - Do NOT make decisions here
        - Do NOT call other tools
        - Only perform the single task

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            ToolResult with execution outcome
        """
        pass

    async def execute_streaming(self, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        """
        Streaming execution — yields progress events, then a final result.

        Default implementation delegates to execute() and yields a single result.
        Override for tools that can report incremental progress (e.g. transcription).
        """
        result = await self.execute(**kwargs)
        yield {"event": "complete", "result": result}

    def validate_params(self, **kwargs: Any) -> tuple[bool, Optional[str]]:
        """
        Validate input parameters.

        Args:
            **kwargs: Parameters to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        for param in self.parameters:
            if param.required and param.name not in kwargs:
                return False, f"Missing required parameter: {param.name}"

            if param.name in kwargs and param.enum is not None:
                if kwargs[param.name] not in param.enum:
                    return (
                        False,
                        f"Invalid value for {param.name}: {kwargs[param.name]}. "
                        f"Allowed: {param.enum}",
                    )

        return True, None

    async def __call__(self, **kwargs: Any) -> ToolResult:
        """
        Execute the tool with validation.

        This is the main entry point for tool execution.
        """
        # Validate parameters
        is_valid, error = self.validate_params(**kwargs)
        if not is_valid:
            return ToolResult.fail(error or "Validation failed")

        # Apply defaults
        for param in self.parameters:
            if param.name not in kwargs and param.default is not None:
                kwargs[param.name] = param.default

        # Execute
        try:
            return await self.execute(**kwargs)
        except Exception as e:
            return ToolResult.fail(f"Execution error: {str(e)}")

    def to_mcp_schema(self) -> dict[str, Any]:
        """
        Convert to MCP tool schema format.

        Returns:
            MCP-compatible tool definition
        """
        properties: dict[str, Any] = {}
        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            properties[param.name] = prop

        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": [p.name for p in self.parameters if p.required],
            },
        }

    def to_openai_schema(self) -> dict[str, Any]:
        """
        Convert to OpenAI function calling schema format.

        Returns:
            OpenAI-compatible function definition
        """
        properties: dict[str, Any] = {}
        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": [p.name for p in self.parameters if p.required],
                },
            },
        }

    def __repr__(self) -> str:
        """String representation."""
        return f"<Tool: {self.name}>"
