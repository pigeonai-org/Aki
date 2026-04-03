"""
PDF Processing Tools

Tools for reading and processing PDF files.
"""

from typing import Any

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore


@ToolRegistry.register
class PDFReadTool(BaseTool):
    """
    PDF reader tool using PyMuPDF.

    Extracts text content and metadata from PDF files.
    """

    name = "pdf_read"
    description = "Read and extract text content from a PDF file. Returns text per page."
    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="Path to the PDF file",
        ),
        ToolParameter(
            name="start_page",
            type="integer",
            description="Start page number (1-indexed, default: 1)",
            required=False,
        ),
        ToolParameter(
            name="end_page",
            type="integer",
            description="End page number (1-indexed, inclusive, default: all)",
            required=False,
        ),
    ]
    concurrency_safe = True

    async def execute(
        self,
        file_path: str,
        start_page: int = 1,
        end_page: int | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """
        Read PDF content.

        Args:
            file_path: Path to PDF file
            start_page: Start page (1-indexed)
            end_page: End page (1-indexed)

        Returns:
            ToolResult with extracted text
        """
        if fitz is None:
            return ToolResult.fail("PyMuPDF not installed. Please install 'pymupdf'.")

        try:
            doc = fitz.open(file_path)

            # Helper to convert 1-indexed to 0-indexed
            start_idx = max(0, start_page - 1)
            end_idx = doc.page_count
            if end_page is not None:
                end_idx = min(doc.page_count, end_page)

            pages = []
            full_text = []

            for page_num in range(start_idx, end_idx):
                page = doc.load_page(page_num)
                text = page.get_text()
                pages.append(
                    {
                        "page_number": page_num + 1,
                        "content": text,
                    }
                )
                full_text.append(text)

            metadata = doc.metadata
            total_pages = doc.page_count
            doc.close()

            return ToolResult.ok(
                data={
                    "file_path": file_path,
                    "metadata": metadata,
                    "pages": pages,
                    "page_count": len(pages),
                    "total_pages": total_pages,
                    "full_text": "\n\n".join(full_text),
                }
            )

        except Exception as e:
            return ToolResult.fail(f"Failed to read PDF: {str(e)}")
