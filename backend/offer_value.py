"""What a vendor offer is worth to you, and whether to take it or wait for the next one.

The vendor fixes one total for an animal (or a wool lot) and fills each of its three offers with random items topped up
with scrap, so every ordinary offer of a visit has the same book value. What differs is the mix: an armoured door is
worth more to a clan than its book value, a horse saddle nothing. Each offer is scored as worth-to-you over book value,
and past offers give the odds that a later one scores better. Offers come one at a time and a turned-down offer is gone,
so this is a stopping problem; after the third, the vendor refuses for 15 minutes, then makes three fresh offers.
"""
import json
from pathlib import Path

# Scrap value of one of each item, solved from recorded offers (MECHANICS.md, vendor_values.py). Rope is per foot.
BOOK = {
    "scrap": 1.0, "metal_fragments": 0.21, "gunpowder": 0.55, "hqm_ore": 3.2,
    "pistol_bullets": 4.4, "incendiary_pistol_bullets": 4.4, "rifle_ammo_556": 4.4,
    "rope": 2.3, "tarp": 8, "targeting_computer": 21, "gears": 28, "blue_keycard": 42, "cctv_camera": 44,
    "horse_saddle": 47, "blueprint_fragment": 47, "smg_body": 79, "rifle_body": 84,
    "semi_automatic_rifle": 234, "high_caliber_revolver": 249, "armored_ladder_hatch": 255,
    "thompson": 320, "custom_smg": 320, "python_revolver": 343, "armored_double_door": 406,
}

# How much of its book value each item is worth to you (1 = face value). Change in settings ("item_worth").
DEFAULT_WORTH = {
    "scrap": 1.0,
    "armored_double_door": 2.0, "armored_ladder_hatch": 2.0,  # what we actually want from the vendor
    "cctv_camera": 1.0, "targeting_computer": 1.0,  # useful
    "metal_fragments": 0.4, "gunpowder": 0.4, "hqm_ore": 0.4,  # fine, but we have plenty
    "pistol_bullets": 0.4, "incendiary_pistol_bullets": 0.4, "rifle_ammo_556": 0.4,
    "gears": 0.5, "blueprint_fragment": 0.5, "blue_keycard": 0.5,
    # tier 2 guns and their parts: plenty from raiding, they end up sold cheaply in the shop
    "semi_automatic_rifle": 0.25, "high_caliber_revolver": 0.25, "python_revolver": 0.25,
    "thompson": 0.25, "custom_smg": 0.25, "smg_body": 0.25, "rifle_body": 0.25,
    "horse_saddle": 0.0, "tarp": 0.0, "rope": 0.0,  # junk
}
UNKNOWN_WORTH = 0.5
RARE_BONUS = 1.5  # a rare-mood offer is worth about 1.3-1.7 times the animal's normal total
RETRY_MARGIN = 0.8  # suggest waiting out the 15-minute refusal only when offer 3 is well below a fresh visit
HISTORY = Path(__file__).with_name("vendor_history.json")  # ordinary offers recorded on the test server


def value(items: list, worth: dict | None = None) -> tuple[float, float, bool]:
    """(book value in scrap, worth to you in scrap, whether any item was unrecognised)."""
    worth = {**DEFAULT_WORTH, **(worth or {})}
    book = mine = 0.0
    unknown = False
    for i in items:
        name = i.get("item")
        amount = i.get("length_ft") or i.get("amount") or 0
        if name not in BOOK:
            unknown = True
            continue
        book += BOOK[name] * amount
        mine += BOOK[name] * amount * worth.get(name, UNKNOWN_WORTH)
    return book, mine, unknown


def _ratios(offers: list, worth: dict | None) -> list[float]:
    out = []
    for items in offers:
        book, mine, unknown = value(items, worth)
        if book > 0 and not unknown:
            out.append(mine / book)
    return out


def thresholds(offers: list, worth: dict | None = None) -> dict:
    """Worth-to-book ratio an offer needs before it's worth taking, by offer number, from past ordinary offers.
    Offer 3 is always worth taking unless a fresh visit after the refusal ('retry') is clearly better."""
    past = _ratios(json.loads(HISTORY.read_text()) + list(offers), worth)
    if not past:
        return {}
    expect = lambda floor: sum(max(r, floor) for r in past) / len(past)  # noqa: E731
    after_2 = sum(past) / len(past)  # offer 3 is taken whatever it is
    after_1 = expect(after_2)  # offer 2, taken if it beats what offer 3 would bring on average
    fresh = expect(after_1)  # a new visit after the 15-minute refusal
    return {1: after_1, 2: after_2, "retry": fresh, "seen": len(past)}


def advise(items: list, number: int, rare: bool, offers: list, worth: dict | None = None) -> dict:
    """Take or turn down this offer. offers: past ordinary offers (item lists) besides the bundled history."""
    book, mine, unknown = value(items, worth)
    bar = thresholds(offers, worth)
    result = {"book": round(book), "worth": round(mine), "unknown": unknown}
    if not bar or book <= 0:
        return result
    total = book / RARE_BONUS if rare else book  # the animal's normal total, which the next offers will have
    if rare:
        need = bar.get(number, 0) * total
        result["take"] = mine >= need
        result["why"] = "rare mood: worth more than his usual offers" if result["take"] else \
            "rare mood, but mostly things you don't want"
    elif number in (1, 2):
        need = bar[number] * total
        result["take"] = mine >= need
        result["why"] = (f"better than the next offers usually are (~{round(need)})" if result["take"] else
                         f"the next offers usually bring ~{round(need)} worth to you")
    else:
        need = RETRY_MARGIN * bar["retry"] * total
        result["take"] = mine >= need
        result["why"] = ("last offer: take it" if result["take"] else
                         f"poor mix: turning it down and coming back in 15 minutes usually brings ~{round(bar['retry'] * total)}")
    return result
