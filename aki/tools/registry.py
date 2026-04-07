"""
Tool Registry

Manages tool registration and lookup.
"""

from typing import Optional, Type

from aki.tools.base import BaseTool


class ToolRegistry:
    """
    Tool Registry for managing available tools.

    Provides registration, lookup, and schema generation.
    """

    _tools: dict[str, Type[BaseTool]] = {}
    _instances: dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool_class: Optional[Type[BaseTool]] = None):
        """
        Decorator to register a tool class.

        Usage:
            @ToolRegistry.register
            class MyTool(BaseTool):
                name = "my_tool"
                ...
        """

        def _register(tc: Type[BaseTool]) -> Type[BaseTool]:
            # Validate the tool class
            if not hasattr(tc, "name") or not tc.name:
                raise ValueError(f"Tool class {tc.__name__} must have a 'name' attribute")

            cls._tools[tc.name] = tc
            return tc

        if tool_class is not None:
            return _register(tool_class)
        return _register

    @classmethod
    def get_class(cls, name: str) -> Type[BaseTool]:
        """
        Get a tool class by name.

        Args:
            name: Tool name

        Returns:
            Tool class

        Raises:
            ValueError: If tool is not registered
        """
        if name not in cls._tools:
            available = list(cls._tools.keys())
            raise ValueError(f"Tool '{name}' not registered. Available: {available}")
        return cls._tools[name]

    @classmethod
    def get(cls, name: str, **init_kwargs) -> BaseTool:
        """
        Get a tool instance by name.

        If kwargs are provided, creates a new instance.
        Otherwise, returns a cached singleton.

        Args:
            name: Tool name
            **init_kwargs: Arguments for tool initialization

        Returns:
            Tool instance
        """
        if init_kwargs:
            # Create new instance with custom config
            tool_class = cls.get_class(name)
            return tool_class(**init_kwargs)

        # Return cached singleton
        if name not in cls._instances:
            tool_class = cls.get_class(name)
            cls._instances[name] = tool_class()
        return cls._instances[name]

    @classmethod
    def list_tools(cls) -> list[str]:
        """List all registered tool names."""
        return list(cls._tools.keys())

    @classmethod
    def get_all_schemas(cls, format: str = "openai") -> list[dict]:
        """
        Get schemas for all registered tools.

        Args:
            format: Schema format ('openai' or 'mcp')

        Returns:
            List of tool schemas
        """
        schemas = []
        for name in cls._tools:
            tool = cls.get(name)
            if format == "mcp":
                schemas.append(tool.to_mcp_schema())
            else:
                schemas.append(tool.to_openai_schema())
        return schemas

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check if a tool is registered."""
        return name in cls._tools

    @classmethod
    def unregister(cls, name: str) -> bool:
        """Remove a tool from the registry. Returns True if it was found."""
        found = name in cls._tools
        cls._tools.pop(name, None)
        cls._instances.pop(name, None)
        return found

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations and instances (useful for testing)."""
        cls._tools.clear()
        cls._instances.clear()
