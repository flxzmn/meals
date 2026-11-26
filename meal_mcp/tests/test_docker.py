"""Docker image for one user over HTTP (docs/DOCKER.md).

The file checks run everywhere. Building and starting the image needs Docker and runs with the
release tests: python -m pytest -m release
"""

import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest
from fastmcp import Client

from scripts.build_mcpb import RUNTIME_PACKAGES

BASE_DIR = Path(__file__).resolve().parent.parent
DOCKERFILE = (BASE_DIR / "Dockerfile").read_text(encoding="utf-8")
IGNORED = (BASE_DIR / ".dockerignore").read_text(encoding="utf-8").split()
COMPOSE = (BASE_DIR / "compose.yaml").read_text(encoding="utf-8")


def test_image_contains_the_same_runtime_files_as_the_bundle():
    copied = set(re.findall(r"^COPY (\S+) \./", DOCKERFILE, re.MULTILINE))
    assert copied == {"main.py", *RUNTIME_PACKAGES}
    assert "COPY pyproject.toml uv.lock ./" in DOCKERFILE, "dependencies from the lock file"
    assert "uv sync --frozen --no-dev" in DOCKERFILE


def test_secrets_and_local_data_stay_out_of_the_image():
    assert {".env", ".venv/", "*.db", "tests/"} <= set(IGNORED)
    assert "USDA_API_KEY" not in DOCKERFILE, "the key comes in at run time, not at build time"


def test_image_serves_http_with_data_on_a_volume():
    for line in ("MEAL_TRANSPORT=http", "MEAL_HTTP_HOST=0.0.0.0", "MEAL_DATA_DIR=/data", "USER meal", "VOLUME /data"):
        assert line in DOCKERFILE
    assert '"127.0.0.1:8000:8000"' in COMPOSE, "port only on this computer"
    assert "MEAL_HTTP_PATH: ${MEAL_HTTP_PATH:?" in COMPOSE, "compose refuses to start without a secret path"


@pytest.mark.release
async def test_image_builds_and_answers(tmp_path):
    docker = shutil.which("docker")
    if docker is None or subprocess.run([docker, "info"], capture_output=True).returncode != 0:
        pytest.skip("Docker not available")
    tag = "meal-mcp:test"
    build = subprocess.run([docker, "build", "-t", tag, str(BASE_DIR)], capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    name = f"meal-test-{uuid.uuid4().hex[:8]}"
    path = "/test-secret/mcp"
    subprocess.run([
        docker, "run", "-d", "--name", name, "-p", "127.0.0.1:18765:8000",
        "-e", "USDA_API_KEY=test-key", "-e", f"MEAL_HTTP_PATH={path}", tag,
    ], check=True, capture_output=True)
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                async with Client(f"http://localhost:18765{path}", timeout=30) as client:
                    rules = (await client.call_tool("find_substitutions", {"ingredients": ["milk"]})).data
                break
            except Exception:
                if time.monotonic() > deadline:
                    logs = subprocess.run([docker, "logs", name], capture_output=True, text=True)
                    pytest.fail("container did not answer:\n" + logs.stdout + logs.stderr)
                time.sleep(1)
        assert "oat milk" in [row["target_ingredient"] for row in rules["milk"]]
        files = subprocess.run([docker, "exec", name, "ls", "/data"], capture_output=True, text=True).stdout
        assert "recipe_mcp.db" in files, "database on the volume"
    finally:
        # -v also removes the anonymous /data volume.
        subprocess.run([docker, "rm", "-f", "-v", name], capture_output=True)
