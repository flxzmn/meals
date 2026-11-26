import os
import sys
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_NAME = "recipe_mcp.db"
# Location up to v1.0: inside the extension folder, which a reinstall deletes.
LEGACY_DB_FILE = BASE_DIR / DB_NAME


def default_data_dir(platform: str = sys.platform, env=os.environ, home: Path | None = None) -> Path:
    """Per-user folder outside the extension, so recipes and rules survive a reinstall."""
    home = home or Path.home()
    if platform == "win32":
        return Path(env.get("APPDATA") or home / "AppData" / "Roaming") / "MealMCP"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "MealMCP"
    return Path(env.get("XDG_DATA_HOME") or home / ".local" / "share") / "meal-mcp"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Keys pasted into Claude Desktop's install dialog may carry a trailing space or newline.
        str_strip_whitespace=True,
    )

    # MEAL_DATA_DIR moves the database and exports, DATABASE_URL replaces only the database.
    meal_data_dir: Path = Field(default_factory=default_data_dir)
    database_url: str = ""
    usda_api_key: str = Field(default="")
    mealdb_base_url: str = "https://www.themealdb.com/api/json/v1/1"
    usda_base_url: str = "https://api.nal.usda.gov/fdc/v1"
    http_timeout_seconds: float = 30.0
    max_concurrent_requests: int = 8
    # Some clients give up on a tool call after 60 s. enrich_recipes stops in time and can be called again.
    enrich_time_budget_seconds: float = 40.0
    log_level: str = "INFO"
    # Claude Desktop starts the server over stdio. "http" serves it on 127.0.0.1 for clients such as
    # ChatGPT, which only reach a server through a public HTTPS address (a tunnel to this port).
    meal_transport: str = "stdio"
    # Only this computer by default; the Docker image sets 0.0.0.0, Docker then decides who reaches the port.
    meal_http_host: str = "127.0.0.1"
    meal_http_port: int = 8000
    # A hard-to-guess path keeps strangers out as long as there is no login.
    meal_http_path: str = "/mcp"
    # Host names a tunnel forwards, comma-separated, e.g. "*.trycloudflare.com".
    meal_allowed_hosts: str = ""

    def model_post_init(self, __context) -> None:
        if not self.database_url:
            self.database_url = self.default_database_url

    @property
    def default_database_file(self) -> Path:
        return self.meal_data_dir / DB_NAME

    @property
    def default_database_url(self) -> str:
        return f"sqlite:///{self.default_database_file.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
