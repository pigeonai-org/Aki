"""
File I/O Tool

General file reading and writing operations.
Pure executor - no decision making.
"""

import os
from pathlib import Path
from typing import Any

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry


def _validate_path(raw: str, *, allow_home: bool = False) -> Path:
    """Resolve path and ensure it doesn't escape the sandbox."""
    resolved = Path(raw).expanduser().resolve()
    cwd = Path.cwd().resolve()
    allowed_roots = [cwd]
    if allow_home:
        allowed_roots.append(Path.home().resolve())
    if not any(resolved == root or str(resolved).startswith(str(root) + os.sep) for root in allowed_roots):
        raise ValueError(f"Path '{resolved}' is outside the allowed directory")
    return resolved


@ToolRegistry.register
class FileReadTool(BaseTool):
    """
    File reader tool.

    Reads content from local files.
    Supports text files of various formats.
    """

    name = "file_read"
    description = (
        "Read content from a local file. Supports text files like .txt, .md, .json, .py, .srt, etc."
    )
    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="Path to the file to read (absolute or relative path)",
        ),
    ]
    concurrency_safe = True

    async def execute(
        self,
        file_path: str,
        encoding: str = "utf-8",
        **kwargs: Any,
    ) -> ToolResult:
        """
        Read file content.

        Args:
            file_path: Path to the file
            encoding: Text encoding

        Returns:
            ToolResult with file content
        """
        try:
            path = _validate_path(file_path)

            if not path.exists():
                return ToolResult.fail(f"File not found: {file_path}")

            if not path.is_file():
                return ToolResult.fail(f"Not a file: {file_path}")

            # Check file size (limit to 1MB for safety)
            size = path.stat().st_size
            if size > 1024 * 1024:
                return ToolResult.fail(
                    f"File too large: {size / 1024 / 1024:.2f}MB (max 1MB). "
                    "Consider reading in chunks."
                )

            content = path.read_text(encoding=encoding)

            return ToolResult.ok(
                data={
                    "content": content,
                    "file_path": str(path),
                    "size": size,
                    "lines": len(content.splitlines()),
                },
                file_path=str(path),
            )
        except UnicodeDecodeError as e:
            return ToolResult.fail(
                f"Failed to decode file with encoding '{encoding}': {str(e)}. "
                "Try a different encoding."
            )
        except PermissionError:
            return ToolResult.fail(f"Permission denied: {file_path}")
        except Exception as e:
            return ToolResult.fail(f"Failed to read file: {str(e)}")


@ToolRegistry.register
class FileWriteTool(BaseTool):
    """
    File writer tool.

    Writes content to local files.
    """

    name = "file_write"
    description = "Write content to a local file. Creates parent directories if needed."
    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="Path to the file to write (absolute or relative path)",
        ),
        ToolParameter(
            name="content",
            type="string",
            description="Content to write to the file",
        ),
    ]

    async def execute(
        self,
        file_path: str,
        content: str,
        encoding: str = "utf-8",
        append: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """
        Write content to file.

        Args:
            file_path: Path to the file
            content: Content to write
            encoding: Text encoding
            append: Append mode

        Returns:
            ToolResult with status
        """
        try:
            path = _validate_path(file_path)

            # Create parent directories if needed
            path.parent.mkdir(parents=True, exist_ok=True)

            mode = "a" if append else "w"
            with open(path, mode, encoding=encoding) as f:
                f.write(content)

            return ToolResult.ok(
                data={
                    "file_path": str(path),
                    "size": len(content.encode(encoding)),
                    "mode": "appended" if append else "written",
                },
            )
        except PermissionError:
            return ToolResult.fail(f"Permission denied: {file_path}")
        except Exception as e:
            return ToolResult.fail(f"Failed to write file: {str(e)}")


@ToolRegistry.register
class FileListTool(BaseTool):
    """
    Directory listing tool.

    Lists files in a directory.
    """

    name = "file_list"
    description = "List files and directories in a given path"
    parameters = [
        ToolParameter(
            name="directory_path",
            type="string",
            description="Path to the directory to list",
        ),
    ]
    concurrency_safe = True

    async def execute(
        self,
        directory_path: str,
        pattern: str = "*",
        recursive: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """
        List directory contents.

        Args:
            directory_path: Path to directory
            pattern: Glob pattern
            recursive: Recursive listing

        Returns:
            ToolResult with file list
        """
        try:
            path = _validate_path(directory_path)

            if not path.exists():
                return ToolResult.fail(f"Directory not found: {directory_path}")

            if not path.is_dir():
                return ToolResult.fail(f"Not a directory: {directory_path}")

            if recursive:
                files = list(path.rglob(pattern))
            else:
                files = list(path.glob(pattern))

            # Limit results
            max_results = 100
            truncated = len(files) > max_results
            files = files[:max_results]

            items = []
            for f in files:
                items.append(
                    {
                        "name": f.name,
                        "path": str(f),
                        "is_dir": f.is_dir(),
                        "size": f.stat().st_size if f.is_file() else None,
                    }
                )

            return ToolResult.ok(
                data={
                    "directory": str(path),
                    "items": items,
                    "count": len(items),
                    "truncated": truncated,
                },
            )
        except PermissionError:
            return ToolResult.fail(f"Permission denied: {directory_path}")
        except Exception as e:
            return ToolResult.fail(f"Failed to list directory: {str(e)}")
