"""
Web Access Tools

Tools for interacting with the web:
- TavilySearchTool: Search the web using Tavily API
- WebPageReadTool: Read and parse content from web pages
"""

from typing import Any, Optional

import httpx
from aki.config import get_settings
from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None  # type: ignore

try:
    import trafilatura
except ImportError:
    trafilatura = None  # type: ignore


@ToolRegistry.register
class TavilySearchTool(BaseTool):
    """
    Web search tool using Tavily API.

    Designed for LLM agents to perform robust web searches.
    """

    name = "web_search"
    description = "Search the web for information using Tavily API. Returns summaries and URLs."
    parameters = [
        ToolParameter(
            name="query",
            type="string",
            description="The search query",
        ),
    ]
    concurrency_safe = True

    def __init__(self) -> None:
        super().__init__()
        self.api_key = get_settings().tavily_api_key

    async def execute(
        self,
        query: str,
        search_depth: str = "basic",
        max_results: int = 5,
        include_domains: Optional[list[str]] = None,
        exclude_domains: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """
        Execute web search.

        Args:
            query: Search query
            search_depth: 'basic' or 'advanced'
            max_results: Number of results
            include_domains: Domains to include
            exclude_domains: Domains to exclude

        Returns:
            ToolResult with search results
        """
        if TavilyClient is None:
            return ToolResult.fail(
                "Tavily Python client not installed. Please install 'tavily-python'."
            )

        if not self.api_key:
            return ToolResult.fail("TAVILY_API_KEY environment variable not set.")

        try:
            client = TavilyClient(api_key=self.api_key)

            response = client.search(
                query=query,
                search_depth=search_depth,
                max_results=max_results,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
            )

            return ToolResult.ok(
                data={
                    "query": query,
                    "results": response.get("results", []),
                    "images": response.get("images", []),
                }
            )
        except Exception as e:
            return ToolResult.fail(f"Search failed: {str(e)}")


@ToolRegistry.register
class WebPageReadTool(BaseTool):
    """
    Web page reader tool.

    Fetches and parses content from a URL using trafilatura for text extraction.
    """

    name = "web_read_page"
    description = "Read and extract main text content from a web page URL."
    parameters = [
        ToolParameter(
            name="url",
            type="string",
            description="URL of the web page to read",
        ),
    ]
    concurrency_safe = True

    async def execute(
        self,
        url: str,
        include_links: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """
        Fetch and parse web page.

        Args:
            url: Page URL
            include_links: Whether to include links in text

        Returns:
            ToolResult with page content
        """
        if trafilatura is None:
            return ToolResult.fail("Trafilatura not installed. Please install 'trafilatura'.")

        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return ToolResult.fail(f"Unsupported URL scheme: {parsed.scheme}")
            # Block private/internal IPs
            import ipaddress
            import socket
            try:
                ip = ipaddress.ip_address(socket.gethostbyname(parsed.hostname or ""))
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    return ToolResult.fail("Access to private/internal addresses is not allowed")
            except (socket.gaierror, ValueError):
                pass  # hostname couldn't be resolved, let httpx handle it

            # First fetch the content
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                html_content = response.text

            # Extract text using trafilatura
            text_content = trafilatura.extract(
                html_content,
                include_links=include_links,
                include_comments=False,
                include_images=False,
            )

            if not text_content:
                return ToolResult.fail(f"Could not extract meaningful text from {url}")

            # Extract metadata if possible
            metadata = trafilatura.extract_metadata(html_content)
            meta_dict = {}
            if metadata:
                meta_dict = {
                    "title": metadata.title,
                    "author": metadata.author,
                    "date": metadata.date,
                    "sitename": metadata.sitename,
                    "categories": metadata.categories,
                }

            return ToolResult.ok(
                data={
                    "url": url,
                    "content": text_content,
                    "metadata": meta_dict,
                    "length": len(text_content),
                }
            )

        except httpx.RequestError as e:
            return ToolResult.fail(f"Network error fetching {url}: {str(e)}")
        except httpx.HTTPStatusError as e:
            return ToolResult.fail(f"HTTP error fetching {url}: {e.response.status_code}")
        except Exception as e:
            return ToolResult.fail(f"Failed to read page: {str(e)}")
