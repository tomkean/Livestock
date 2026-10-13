"""User settings kept as JSON in the data folder."""
import json

from config import SETTINGS_PATH

DEFAULTS = {
    # Where the card and the name sit in a captured frame, as fractions [x, y, w, h] of the frame size.
    "card_box": None,
    "name_box": None,
    # Unknown in game so far; only used to show a count against capacity.
    "pen_capacity": {"M": 4, "F": 8},
    # How animals get to the barn (Plan page): "lead" = leading on foot (one at a time), "small" flatbed
    # (1 sheep or lamb) or "large" flatbed (2 sheep/lambs, or 1 cow), on whatever vehicle.
    "vehicle": "small",
    # Genes the breeding target needs Good/Good on. Leave out ones you don't care about (e.g. D if dung is worthless
    # to you): the plan gets much faster. A full god animal is all five.
    "target_genes": "DLYFH",
    # False = live server: only the top row is visible, so every calculation infers hidden copies from top rows and
    # family. True = test server with livestock.panelalleles: use captured second rows (debugging and validation only).
    "second_row_visible": False,
    # Pools mode rooms: harems (one ram each, mating freely) and a holding room. Names are free text.
    # 5 ewes: a clump of 6 sheep bottomed out at 73% personal space, just above the 70% breeding threshold.
    # Where the player is (picked on the Capture tab until Rust+ can tell): a building name, "Vendor" or "".
    # Automatic capture files every animal it recognises under this building, and captures are tagged with it.
    "location": "",
    # What vendor items are worth to you, as a fraction of their scrap value (offer_value.DEFAULT_WORTH has the rest):
    # e.g. {"horse_saddle": 0, "armored_double_door": 2}. The vendor toast says whether to take each offer.
    "item_worth": {},
    # What the breeding plan aims for: "god" (Good/Good on the target genes) or "wool" (production: lambs that show
    # green Y and aren't inbred).
    "goal": "god",
    # Safe Mode, for time away: rooms are single-sex (no breeding) and the best animals spread out. Off returns to `goal`.
    "safe_mode": False,
    "pools": {"harems": ["Harem #1", "Harem #2"], "holding": "Death Row", "harem_ewes": 7, "holding_size": 7, "site_cap": 9},
}


def load() -> dict:
    data = dict(DEFAULTS)
    if SETTINGS_PATH.exists():
        data.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
    data["pools"] = dict(data.get("pools") or {})
    data["pools"]["rooms"] = rooms_of(data["pools"])
    return data


def rooms_of(pools: dict) -> list[dict]:
    """The farm's rooms: a name and how many animals it holds in good health. Rooms have no fixed job - the plan
    decides each round which hold breeding pairs and which hold rams or ewes. Older settings (harems, holding rooms
    with jobs) are turned into rooms, with the capacities those jobs implied."""
    if pools.get("rooms"):
        return [{"name": str(r["name"]), "capacity": max(1, int(r.get("capacity") or 1))} for r in pools["rooms"] if r.get("name")]
    rooms = [{"name": h, "capacity": 3} for h in pools.get("harems") or []]
    holding = pools.get("holding") or []
    for h in ([holding] if isinstance(holding, str) else holding):
        if h not in [r["name"] for r in rooms]:
            single = h in (pools.get("holding_by_sex") or {}).values()
            rooms.append({"name": h, "capacity": 1 if single else int(pools.get("holding_size") or 5)})
    return rooms


def save(changes: dict) -> dict:
    data = load()
    data.update({k: v for k, v in changes.items() if k in DEFAULTS})
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data
