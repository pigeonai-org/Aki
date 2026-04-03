"""
MCP Integration Test: Aki <-> DatingApp Backend

Tests bidirectional MCP communication:
1. Aki (client) -> DatingApp MCP server (streamable HTTP)
2. DatingApp (client) -> Aki MCP server (stdio)
"""

import asyncio

from aki.mcp.client.client import MCPClient, MCPServerConfig


# ---------------------------------------------------------------------------
# Test 1: Aki calls DatingApp MCP tools (streamable HTTP)
# ---------------------------------------------------------------------------

async def test_aki_to_dating_app():
    """Aki connects to DatingApp MCP server and lists/calls tools."""
    print("\n" + "=" * 60)
    print("TEST 1: Aki -> DatingApp MCP (streamable HTTP)")
    print("=" * 60)

    config = MCPServerConfig(
        name="dating-app",
        transport="streamable-http",
        url="http://localhost:8001/mcp",
    )

    client = MCPClient()

    async with client.connect(config) as session:
        # List tools
        tools = await client.list_tools(session, config.name)
        print(f"\n[OK] Connected! Found {len(tools)} tools:")
        for t in tools:
            print(f"  - {t.name}: {t.description[:60]}...")

        # Call get_recommendations (will likely fail with DB error, but proves MCP works)
        print("\n[...] Calling get_recommendations(user_id='test-user-123')...")
        try:
            result = await client.call_tool(
                session,
                "get_recommendations",
                {"user_id": "test-user-123", "limit": 3},
            )
            print(f"[OK] Result: {str(result)[:200]}")
        except Exception as e:
            print(f"[!] Tool returned error (expected if no DB): {e}")

        # Call get_shareable_profile
        print("\n[...] Calling get_shareable_profile(user_id='test-user-123')...")
        try:
            result = await client.call_tool(
                session,
                "get_shareable_profile",
                {"user_id": "test-user-123"},
            )
            print(f"[OK] Result: {str(result)[:200]}")
        except Exception as e:
            print(f"[!] Tool returned error (expected if no DB): {e}")

    print("\n[OK] Test 1 complete - Aki successfully communicated with DatingApp MCP")


# ---------------------------------------------------------------------------
# Test 2: DatingApp calls Aki MCP tools (stdio)
# ---------------------------------------------------------------------------

async def test_dating_app_to_aki():
    """Simulate DatingApp connecting to Aki MCP server via stdio."""
    print("\n" + "=" * 60)
    print("TEST 2: DatingApp -> Aki MCP (stdio)")
    print("=" * 60)

    config = MCPServerConfig(
        name="aki",
        transport="stdio",
        command="uv",
        args=["run", "aki-mcp-server"],
    )

    client = MCPClient()

    async with client.connect(config) as session:
        # List tools
        tools = await client.list_tools(session, config.name)
        print(f"\n[OK] Connected! Found {len(tools)} tools:")
        for t in tools:
            print(f"  - {t.name}: {t.description[:60]}...")

        # Call translate_text
        print("\n[...] Calling translate_text(text='Hello', target_language='zh')...")
        try:
            result = await client.call_tool(
                session,
                "translate_text",
                {"text": "Hello, how are you?", "target_language": "zh"},
            )
            print(f"[OK] Result: {str(result)[:200]}")
        except Exception as e:
            print(f"[!] Tool returned error: {e}")

    print("\n[OK] Test 2 complete - DatingApp successfully communicated with Aki MCP")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("MCP Integration Test: Aki <-> DatingApp")
    print("Make sure DatingApp MCP server is running on localhost:8000")
    print("  cd /Users/myyyth/Documents/DatingApp/backend")
    print("  uv run python -m mcp_server.server")

    choice = input("\nRun which test? [1=Aki->DatingApp, 2=DatingApp->Aki, 3=both]: ").strip()

    if choice in ("1", "3"):
        await test_aki_to_dating_app()

    if choice in ("2", "3"):
        await test_dating_app_to_aki()

    if choice not in ("1", "2", "3"):
        print("Running test 1 (Aki -> DatingApp) by default...")
        await test_aki_to_dating_app()

    print("\n" + "=" * 60)
    print("All tests complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
