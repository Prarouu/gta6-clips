"""Loads settings/keywords/creators/permissions. Credentials come only from environment variables."""
import json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "gta6.db"
LOG_DIR = DATA_DIR / "logs"
REPORT_DIR = DATA_DIR / "reports"


def _load(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def load_settings() -> dict:
    return _load("settings.json")


def load_keywords() -> dict:
    return _load("keywords.json")


def load_creators() -> list:
    return _load("creators.json").get("channels", [])


def load_permissions() -> list:
    return _load("permissions.json").get("creators", [])


def youtube_api_key() -> str:
    return os.environ.get("YOUTUBE_API_KEY", "").strip()
