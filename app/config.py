import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    source_mode: str = field(default_factory=lambda: os.getenv("SOURCE_MODE", "live"))
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
    public_base_url: str = field(default_factory=lambda: os.getenv("PUBLIC_BASE_URL", "http://localhost:8000"))
    max_page_bytes: int = 1_500_000
    fetch_timeout_s: float = 8.0
    max_members: int = 12
    max_venues: int = 8


def get_settings() -> Settings:
    return Settings()
