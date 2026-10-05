"""User settings kept as JSON in the data folder."""
import json

from config import SETTINGS_PATH

DEFAULTS = {
    # Where the card and the name sit in a captured frame, as fractions [x, y, w, h] of the frame size.
    "card_box": None,
    "name_box": None,
    # Unknown in game so far; only used to show a count against capacity.
    "pen_capacity": {"M": 4, "F": 8},
    # Truck for barn trips: "single" (1 sheep or lamb) or "double" module (2 sheep/lambs, or 1 cow).
    "vehicle": "single",
}


def load() -> dict:
    data = dict(DEFAULTS)
    if SETTINGS_PATH.exists():
        data.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
    return data


def save(changes: dict) -> dict:
    data = load()
    data.update({k: v for k, v in changes.items() if k in DEFAULTS})
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data
