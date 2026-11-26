"""HTTP transport for clients such as ChatGPT, which reach the server through a tunnel instead of starting it."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastmcp import Client

import main  # noqa: F401  registers all MCP tools
from mcp_tools.server import mcp

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_PATH = "/test-secret/mcp"


async def test_read_only_and_destructive_tools_are_marked():
    tools = {tool.name: tool.annotations for tool in await mcp.list_tools()}
    assert tools["get_recipes"].readOnlyHint is True
    assert tools["adapt_recipes"].readOnlyHint is True, "adapt_recipes stores nothing"
    assert tools["delete_recipes"].destructiveHint is True
    # Tools that write, also only to the nutrition cache, must stay unmarked so the client can ask first.
    for name in ("save_recipes", "enrich_recipes", "compare_nutrition", "import_data"):
        assert not (tools[name] and tools[name].readOnlyHint), name


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def http_server(tmp_path):
    port = free_port()
    env = {key: value for key, value in os.environ.items() if key not in {"DATABASE_URL", "USDA_API_KEY"}}
    env.update({
        "MEAL_TRANSPORT": "http", "MEAL_HTTP_PORT": str(port), "MEAL_HTTP_PATH": SECRET_PATH,
        "MEAL_ALLOWED_HOSTS": "*.trycloudflare.com", "MEAL_DATA_DIR": str(tmp_path), "USDA_API_KEY": "test-key",
    })
    process = subprocess.Popen(
        [sys.executable, str(BASE_DIR / "main.py")], env=env, cwd=str(tmp_path),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            assert process.poll() is None, "server stopped during start"
            time.sleep(0.1)
    else:
        process.kill()
        pytest.fail("server did not start")
    yield f"http://127.0.0.1:{port}"
    process.kill()
    process.wait()


async def test_server_answers_over_http(http_server, tmp_path):
    async with Client(http_server + SECRET_PATH) as client:
        tools = {tool.name for tool in await client.list_tools()}
        assert {"get_recipes", "find_substitutions"} <= tools
        rules = (await client.call_tool("find_substitutions", {"ingredients": ["milk"]})).data
        assert "oat milk" in [row["target_ingredient"] for row in rules["milk"]], "seed rules are loaded"
    assert (tmp_path / "recipe_mcp.db").exists()


def test_http_checks_path_and_host(http_server):
    request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}}
    headers = {"Accept": "application/json, text/event-stream"}

    def post(path: str, host: str | None = None) -> int:
        return httpx.post(http_server + path, json=request, headers={**headers, **({"Host": host} if host else {})}).status_code

    assert post(SECRET_PATH) == 200
    assert post("/mcp") == 404, "only the configured path answers"
    assert post(SECRET_PATH, "evil.example") == 421, "host check is on (FastMCP leaves it off by default)"
    assert post(SECRET_PATH, "abc.trycloudflare.com") == 200, "tunnel host names from MEAL_ALLOWED_HOSTS pass"
