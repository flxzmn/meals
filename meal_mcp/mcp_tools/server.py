import sys

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware


class ToolCallLog(Middleware):
    """Write each tool name and outcome to stderr, which Claude Desktop stores in its MCP log.

    scripts/run_evals.py reads these lines. Arguments stay out of the log: they can hold personal data.
    """

    async def on_call_tool(self, context, call_next):
        name = context.message.name
        try:
            result = await call_next(context)
        except Exception:
            print(f"TOOL_CALL {name} error", file=sys.stderr, flush=True)
            raise
        print(f"TOOL_CALL {name} ok", file=sys.stderr, flush=True)
        return result


# Hints for the client: ChatGPT asks the user to confirm every tool not marked read-only.
READ_ONLY = {"readOnlyHint": True}
DESTRUCTIVE = {"readOnlyHint": False, "destructiveHint": True}

mcp = FastMCP(name="Recipe MCP", instructions="Search, save, enrich and analyze recipes in bulk.")
mcp.add_middleware(ToolCallLog())
