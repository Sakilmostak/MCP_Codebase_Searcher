import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    # Use the local python to run mcp_server.py
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["src/mcp_server.py"],
        env=os.environ.copy()
    )

    print("Starting client...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Request tools
            tools = await session.list_tools()
            print("Tools available:", [t.name for t in tools.tools])
            
            # Find the search_codebase tool
            search_tool = next((t for t in tools.tools if t.name == "search_codebase"), None)
            if not search_tool:
                print("search_codebase tool not found.")
                return

            print("\nCalling search_codebase on src/ ...")
            
            # Setup notification handler to catch logs
            session.on_notification = lambda n: print(f"NOTIFICATION RECEIVED: {n}")
            
            try:
                result = await session.call_tool(
                    "search_codebase",
                    arguments={
                        "query": "FastMCP",
                        "paths": ["src/mcp_server.py"]
                    }
                )
                print("\nResult:")
                print(result)
            except Exception as e:
                print(f"Error calling tool: {e}")

if __name__ == "__main__":
    asyncio.run(main())
