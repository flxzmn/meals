"""Build the MCPB bundle from an allowlist of runtime files.

Usage:
    python scripts/build_mcpb.py                  # build
    python scripts/build_mcpb.py --sync-manifest  # copy tool list from the server into manifest.json, then build

Builds dist/meal-<version>.mcpb with server type "uv" (manifest_version 0.4): Claude Desktop
installs the dependencies from pyproject.toml / uv.lock itself, so no Python setup is needed.
The mcpb CLI 0.3.5 does not know type "uv", so the bundle is zipped by this script.

Using an allowlist keeps .venv, .env, the SQLite database, tests and old builds out of the bundle.

Use --sync-manifest after changing tool names or docstrings. Unlike
"mcpb pack --update" it only replaces the tool list and keeps user_config
and everything else; it adds no "_meta" key.
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STAGE_DIR = BASE_DIR / "build" / "mcpb"
DIST_DIR = BASE_DIR / "dist"

RUNTIME_FILES = ["main.py", "manifest.json", "README.md", "icon.png", "LICENSE", "pyproject.toml", "uv.lock"]
RUNTIME_PACKAGES = ["config", "db", "repo", "services", "mcp_tools", "data"]


def stage(target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in RUNTIME_FILES:
        shutil.copy2(BASE_DIR / name, target / name)
    for name in RUNTIME_PACKAGES:
        shutil.copytree(
            BASE_DIR / name,
            target / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.db"),
        )


def zip_dir(source: Path, output: Path) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source).as_posix())


def sync_manifest() -> None:
    # Starting the server creates a database; keep it away from the user's real data folder.
    os.environ["MEAL_DATA_DIR"] = tempfile.mkdtemp()
    sys.path.insert(0, str(BASE_DIR))
    import main as server  # noqa: F401  registers all MCP tools
    from mcp_tools.server import mcp

    tools = asyncio.run(mcp.list_tools())
    manifest_path = BASE_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tools"] = sorted(
        ({"name": tool.name, "description": tool.description or ""} for tool in tools),
        key=lambda tool: tool["name"],
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Synced {len(tools)} tools into manifest.json")


def main() -> int:
    if "--sync-manifest" in sys.argv[1:]:
        sync_manifest()

    manifest = json.loads((BASE_DIR / "manifest.json").read_text(encoding="utf-8"))
    output = DIST_DIR / f"meal-{manifest['version']}.mcpb"
    DIST_DIR.mkdir(exist_ok=True)

    stage(STAGE_DIR)
    zip_dir(STAGE_DIR, output)
    print(f"Built {output} ({output.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
