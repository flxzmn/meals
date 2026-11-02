"""Release test for the MCPB bundle.

Builds dist/meal-<version>.mcpb with scripts/build_mcpb.py, unpacks it and
checks what Claude Desktop will see: a manifest without unknown keys, the
user_config for the USDA key, no secrets or local files in the bundle, and a
server that starts from the unpacked bundle with uv, like the host does.

Opt-in, because it takes a while on the first run (uv installs the dependencies):

    python -m pytest -m release
"""

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

pytestmark = pytest.mark.release

BASE_DIR = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((BASE_DIR / "manifest.json").read_text(encoding="utf-8"))
BUNDLE = BASE_DIR / "dist" / f"meal-{MANIFEST['version']}.mcpb"
MAX_BUNDLE_BYTES = 1024 * 1024

# Top-level keys of an MCPB manifest. Claude Desktop rejects anything else,
# e.g. the "_meta" key that "mcpb pack --update" writes.
ALLOWED_MANIFEST_KEYS = {
    "manifest_version", "dxt_version", "name", "display_name", "version", "description",
    "long_description", "author", "repository", "homepage", "documentation", "support",
    "icon", "icons", "screenshots", "server", "tools", "tools_generated", "prompts",
    "prompts_generated", "keywords", "license", "privacy_policies", "compatibility",
    "user_config", "localization",
}
RUNTIME_ROOTS = {
    "main.py", "manifest.json", "README.md", "icon.png", "LICENSE", "pyproject.toml", "uv.lock",
    "config", "db", "repo", "services", "mcp_tools", "data",
}
FORBIDDEN_SUFFIXES = (".env", ".db", ".mcpb", ".pyc")


@pytest.fixture(scope="module")
def bundle() -> Path:
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "scripts" / "build_mcpb.py")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return BUNDLE


@pytest.fixture(scope="module")
def unpacked(bundle, tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp("bundle")
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(target)
    return target


@pytest.fixture(scope="module")
def bundled_manifest(unpacked) -> dict:
    return json.loads((unpacked / "manifest.json").read_text(encoding="utf-8"))


def test_bundle_is_small(bundle):
    assert bundle.stat().st_size < MAX_BUNDLE_BYTES


def test_bundle_contains_only_runtime_files(bundle, unpacked):
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
    assert {name.split("/")[0] for name in names} == RUNTIME_ROOTS
    assert not [name for name in names if name.endswith(FORBIDDEN_SUFFIXES) or "__pycache__" in name]
    assert not (unpacked / "server").exists()  # the spec forbids server/lib and server/venv for type uv


def test_bundle_contains_no_api_key(bundle):
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        pytest.skip("no local .env to compare against")
    keys = [
        line.split("=", 1)[1].strip()
        for line in env_file.read_text(encoding="utf-8").splitlines()
        if line.startswith("USDA_API_KEY=") and line.split("=", 1)[1].strip()
    ]
    with zipfile.ZipFile(bundle) as archive:
        content = b"".join(archive.read(name) for name in archive.namelist())
    assert not [key for key in keys if key.encode() in content]


def test_manifest_has_no_unknown_keys(bundled_manifest):
    assert set(bundled_manifest) <= ALLOWED_MANIFEST_KEYS


def test_manifest_matches_repository(bundled_manifest):
    assert bundled_manifest == MANIFEST


def test_manifest_presents_the_extension(bundled_manifest, unpacked):
    for key in ("display_name", "description", "long_description", "keywords", "license", "repository"):
        assert bundled_manifest[key]
    assert bundled_manifest["author"]["name"]
    assert all(tool["description"] for tool in bundled_manifest["tools"])
    assert (unpacked / bundled_manifest["icon"]).read_bytes().startswith(b"\x89PNG")


def test_version_matches_pyproject():
    pyproject = (BASE_DIR / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{MANIFEST["version"]}"' in pyproject


def test_manifest_asks_for_usda_key(bundled_manifest):
    option = bundled_manifest["user_config"]["usda_api_key"]
    assert option["required"] is True
    assert option["sensitive"] is True
    assert bundled_manifest["server"]["mcp_config"]["env"] == {"USDA_API_KEY": "${user_config.usda_api_key}"}


def test_manifest_uses_uv(bundled_manifest):
    assert bundled_manifest["manifest_version"] == "0.4"
    assert bundled_manifest["server"]["type"] == "uv"
    assert bundled_manifest["server"]["entry_point"] == "main.py"


async def test_server_starts_from_bundle(unpacked, bundled_manifest, tmp_path):
    """Runs the bundle like the host: uv installs the locked dependencies into a fresh environment."""
    uv = shutil.which("uv") or shutil.which("uv", path=str(Path(sys.executable).parent))
    if uv is None:
        pytest.skip("uv not found (install with: python -m pip install uv)")
    env = {key: value for key, value in os.environ.items() if key not in {"DATABASE_URL", "USDA_API_KEY", "VIRTUAL_ENV"}}
    env["USDA_API_KEY"] = "release-test-key"
    env["MEAL_DATA_DIR"] = str(tmp_path)
    transport = StdioTransport(
        command=uv,
        args=["run", "--frozen", "--no-dev", "--directory", str(unpacked), "main.py"],
        env=env,
        cwd=str(unpacked.parent),
    )
    async with Client(transport, timeout=300) as client:
        tools = {tool.name for tool in await client.list_tools()}
        assert tools == {tool["name"] for tool in bundled_manifest["tools"]}
        result = await client.call_tool(
            "suggest_substitutions", {"ingredients": ["halloumi"], "constraints": {"diet": "vegan"}}
        )
        assert result.data["status"] == "candidates_required"
        rules = await client.call_tool("find_substitutions", {"ingredients": ["milk"]})
        assert "oat milk" in [row["target_ingredient"] for row in rules.data["milk"]], "seed rules are loaded"

    assert (unpacked / ".venv").exists(), "uv must create its own environment"
    assert (tmp_path / "recipe_mcp.db").exists(), "database must be created in the data folder"
    assert not (unpacked / "recipe_mcp.db").exists(), "a reinstall deletes the install directory"
