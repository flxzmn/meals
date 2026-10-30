"""Build the MCPB bundles from an allowlist of runtime files.

Usage:
    python scripts/build_mcpb.py                  # build
    python scripts/build_mcpb.py --sync-manifest  # copy tool list from the server into manifest.json, then build

Builds two bundles from the same files:

- dist/meal-<version>.mcpb: server type "python" (manifest.json as is). Claude Desktop starts
  the system python, which needs the packages from requirements.txt. Packed with the mcpb CLI.
- dist/meal-<version>-uv.mcpb: server type "uv" (manifest_version 0.4). The host installs the
  dependencies from pyproject.toml / uv.lock itself, so no Python setup is needed (Sprint 11).
  The mcpb CLI 0.3.5 does not know type "uv" yet, so this bundle is zipped by this script.
  Recommended; tested in Claude Desktop on Windows and macOS.

Using an allowlist keeps .venv, .env, the SQLite database, tests and old builds out of the bundles.

Use --sync-manifest after changing tool names or docstrings. Unlike
"mcpb pack --update" it only replaces the tool list and keeps user_config
and everything else; it adds no "_meta" key.
"""

import asyncio
import copy
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STAGE_DIR = BASE_DIR / "build" / "mcpb"
UV_STAGE_DIR = BASE_DIR / "build" / "mcpb-uv"
DIST_DIR = BASE_DIR / "dist"

RUNTIME_FILES = ["main.py", "manifest.json", "README.md", "requirements.txt", "icon.png", "LICENSE"]
RUNTIME_PACKAGES = ["config", "db", "repo", "services", "mcp_tools"]
UV_FILES = ["pyproject.toml", "uv.lock"]


def stage(target: Path, files: list[str]) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in files:
        shutil.copy2(BASE_DIR / name, target / name)
    for name in RUNTIME_PACKAGES:
        shutil.copytree(
            BASE_DIR / name,
            target / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.db"),
        )


def uv_manifest(manifest: dict) -> dict:
    """The python manifest turned into a manifest for server type "uv"."""
    result = copy.deepcopy(manifest)
    result["manifest_version"] = "0.4"
    env = {key: value for key, value in manifest["server"]["mcp_config"].get("env", {}).items() if key != "PYTHONPATH"}
    result["server"] = {
        "type": "uv",
        "entry_point": manifest["server"]["entry_point"],
        # The host manages execution for type "uv"; mcp_config only passes the user_config values.
        "mcp_config": {
            "command": "uv",
            "args": ["run", "--directory", "${__dirname}", manifest["server"]["entry_point"]],
            "env": env,
        },
    }
    return result


def zip_dir(source: Path, output: Path) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source).as_posix())


def sync_manifest() -> None:
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
    args = sys.argv[1:]
    if "--sync-manifest" in args:
        args.remove("--sync-manifest")
        sync_manifest()

    mcpb = shutil.which("mcpb")
    if mcpb is None:
        print("mcpb CLI not found on PATH.", file=sys.stderr)
        return 1

    manifest = json.loads((BASE_DIR / "manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    output = DIST_DIR / f"meal-{version}.mcpb"
    uv_output = DIST_DIR / f"meal-{version}-uv.mcpb"
    DIST_DIR.mkdir(exist_ok=True)

    stage(STAGE_DIR, RUNTIME_FILES)
    result = subprocess.run([mcpb, "pack", str(STAGE_DIR), str(output), *args])
    if result.returncode != 0:
        return result.returncode
    print(f"Built {output} ({output.stat().st_size / 1024:.1f} KB)")

    stage(UV_STAGE_DIR, [name for name in RUNTIME_FILES if name != "requirements.txt"] + UV_FILES)
    (UV_STAGE_DIR / "manifest.json").write_text(
        json.dumps(uv_manifest(manifest), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    zip_dir(UV_STAGE_DIR, uv_output)
    print(f"Built {uv_output} ({uv_output.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
