from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_FILE = BASE_DIR / "recipe_mcp.db"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Keys pasted into Claude Desktop's install dialog may carry a trailing space or newline.
        str_strip_whitespace=True,
    )

    database_url: str = f"sqlite:///{DB_FILE.as_posix()}"
    usda_api_key: str = Field(default="")
    mealdb_base_url: str = "https://www.themealdb.com/api/json/v1/1"
    usda_base_url: str = "https://api.nal.usda.gov/fdc/v1"
    http_timeout_seconds: float = 30.0
    max_concurrent_requests: int = 8
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
