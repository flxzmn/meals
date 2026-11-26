"""Smoke test for a running HTTP server (docs/SCHNELLSTART.md).

Runs inside the container, so no local Python is needed. Keep this file ASCII: PowerShell 5.1 pipes
text to native programs as ASCII.

    Get-Content scripts\\smoke_test.py | docker compose exec -T meal python - [https://abc.trycloudflare.com]

Without an address it checks the server inside the container; with the tunnel address it checks the
public way that ChatGPT uses. The secret path comes from MEAL_HTTP_PATH.
"""

import asyncio
import os
import sys

import httpx
from fastmcp import Client

EXPECTED_TOOLS = 31


def check(ok: bool, text: str) -> bool:
    print(("OK    " if ok else "FEHLER") + "  " + text)
    return ok


async def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
    path = os.environ.get("MEAL_HTTP_PATH", "/mcp")
    url = base + path
    print(f"Server: {base}<geheimer Pfad>\n")

    results = []
    async with Client(url, timeout=60) as client:
        tools = await client.list_tools()
        read_only = [tool for tool in tools if tool.annotations and tool.annotations.read_only_hint]
        results.append(check(len(tools) == EXPECTED_TOOLS, f"{len(tools)} Tools, davon {len(read_only)} nur lesend"))

        rules = (await client.call_tool("find_substitutions", {})).data
        count = sum(len(rows) for rows in rules.values())
        results.append(check(count >= 30, f"{count} Ersatzregeln (frische Daten: 30)"))

        milk = (await client.call_tool("find_substitutions", {"ingredients": ["milk"]})).data
        targets = [row["target_ingredient"] for row in milk.get("milk", [])]
        results.append(check("oat milk" in targets, "Milch -> Hafermilch gefunden"))

    async with httpx.AsyncClient(timeout=30) as http:
        response = await http.post(base + "/mcp", json={})
    results.append(check(response.status_code == 404, f"ohne geheimen Pfad: {response.status_code} (erwartet 404)"))

    print("\nAlles in Ordnung." if all(results) else "\nMindestens ein Check ist fehlgeschlagen.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
