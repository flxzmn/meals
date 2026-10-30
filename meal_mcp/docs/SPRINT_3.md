# Sprint 3

## Goal

Enrich several saved recipes with USDA nutrition data in one MCP tool call.

## Acceptance

1. Imports work.
2. TheMealDB bulk search works.
3. FastMCP starts.
4. USDA enrichment reads `USDA_API_KEY` from `.env`.
5. Previously cached ingredients do not trigger another USDA request.
6. Missing ingredients and API errors are returned to the caller.
7. `python -m pytest` passes.
