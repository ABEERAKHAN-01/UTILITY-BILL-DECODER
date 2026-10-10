"""Settings loaded from the .env file in the project root (keys are never hard-coded)."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

# Competition-approved models only (anything else is disqualification).
ALLOWED_MODELS = {
    "anthropic": {"claude-haiku-4-5"},
    "google": {"gemini-3.5-flash-lite", "gemini-3.1-flash-lite"},
    "openai": {"gpt-4.1-mini", "gpt-5-mini"},
}


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    api_key: str
    request_delay: float = 0.0
    max_workers: int = 2
    cache_dir: str = ".cache"
    max_image_side: int = 2400


def _clean(value: str | None) -> str:
    return (value or "").strip().strip("\"'").strip()


def _number(name: str, default, cast):
    raw = _clean(os.getenv(name))
    if not raw:
        return default
    try:
        return cast(raw)
    except ValueError:
        sys.exit(f"ERROR: {name} in .env must be a number, got {raw!r}")


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    provider = _clean(os.getenv("MODEL_PROVIDER")).lower()
    model = _clean(os.getenv("MODEL_NAME"))
    key = _clean(os.getenv("API_KEY"))

    if provider not in ALLOWED_MODELS:
        sys.exit(f"ERROR: MODEL_PROVIDER must be one of {sorted(ALLOWED_MODELS)}, got {provider!r}")
    if model not in ALLOWED_MODELS[provider]:
        sys.exit(f"ERROR: model {model!r} is not allowed for {provider}. "
                 f"Allowed: {sorted(ALLOWED_MODELS[provider])}")
    if not key or key.lower() in {"your-api-key-here", "your_api_key_here"}:
        sys.exit("ERROR: API_KEY is missing. Copy .env.example to .env and paste your key.")

    cache_dir = _clean(os.getenv("CACHE_DIR")) or ".cache"
    if not Path(cache_dir).is_absolute():
        cache_dir = str(ROOT / cache_dir)
    return Settings(
        provider=provider, model=model, api_key=key,
        request_delay=_number("REQUEST_DELAY_SECONDS", 0.0, float),
        max_workers=max(1, _number("MAX_WORKERS", 2, int)),
        cache_dir=cache_dir,
        max_image_side=_number("MAX_IMAGE_SIDE", 2400, int),
    )
