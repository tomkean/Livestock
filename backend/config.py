"""Filesystem locations and port. Runtime data lives beside the repo, not in it."""
import os
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = REPO_DIR.parent

DATA_DIR = Path(os.environ.get("LIVESTOCK_DATA", PROJECT_DIR / "data"))
BUILD_DIR = Path(os.environ.get("LIVESTOCK_BUILD", PROJECT_DIR / "build" / "frontend"))
CAPTURE_DIR = DATA_DIR / "captures"
CARD_DIR = DATA_DIR / "cards"
NAME_DIR = DATA_DIR / "names"
DB_PATH = DATA_DIR / "livestock.db"
SETTINGS_PATH = DATA_DIR / "settings.json"

PORT = int(os.environ.get("LIVESTOCK_PORT", 8100))

for d in (DATA_DIR, CAPTURE_DIR, CARD_DIR, NAME_DIR):
    d.mkdir(parents=True, exist_ok=True)
