"""Runtime configuration from environment variables (BACKEND_BRIEF.md §4).

The service must start and serve every endpoint except /assist/* with
LLM_ENABLED=false and no API key present.
"""
import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    llm_enabled: bool
    llm_api_key: str | None
    cors_origins: list[str]
    default_radius_km: int
    moratorium_treatment: str


def _load_settings() -> Settings:
    llm_enabled = os.environ.get("LLM_ENABLED", "false").strip().lower() == "true"
    cors_raw = os.environ.get("CORS_ORIGINS", "")
    cors_origins = [origin.strip() for origin in cors_raw.split(",") if origin.strip()]
    return Settings(
        llm_enabled=llm_enabled,
        llm_api_key=os.environ.get("LLM_API_KEY") or None,
        cors_origins=cors_origins,
        default_radius_km=int(os.environ.get("DEFAULT_RADIUS_KM", "25")),
        moratorium_treatment=os.environ.get("MORATORIUM_TREATMENT", "capitalise"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return _load_settings()
