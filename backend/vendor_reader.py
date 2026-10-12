"""Reads the barn vendor's Sale panel: whose sale it is, which offer, and what's offered.

Layout (measured at 3840x2160) hangs off the "REWARDS" label: the name just above it, three item slots below it, and the
Stablehand dialogue box further up, whose first line says which offer this is ("Yep, that will do nicely..." for the
first, "Alright, forget that one..." for the next, "You've caught me in a rare mood..." for a bonus offer). Items are
recognised against a library of icons cut from labelled sales (vendor_items/<item>/*.png); unknown icons are kept so
they can be labelled later.
"""
import re
from pathlib import Path

import cv2
import numpy as np

from card_reader import _tesseract_ready, pytesseract

TEMPLATE_DIR = Path(__file__).parent / "vendor_templates"
LIBRARY_DIR = Path(__file__).parent / "vendor_items"
BASE_WIDTH = 3840

ANCHOR_MIN = 0.8
NAME_BOX = (0, -66, 520, 48)  # x, y, w, h from the REWARDS label's top-left
SLOT_FIRST = (11, 45)  # top-left of the first item slot
SLOT_SIZE = 179
SLOT_STEP = 192
QTY_BOX = (70, 130, 108, 44)  # inside a slot: the "x620" / "6ft" in its bottom-right corner (light grey text)
ICON_BOX = (6, 6, 167, 112)  # inside a slot: the icon, clear of the quantity text
DIALOGUE_BELOW_HEADER = (35, 70, 900, 115)  # from the Stablehand label: the dialogue's first two lines
ITEM_MATCH = 0.72
QTY_TEXT = 115  # grey level: the quantity text is ~160, the slot behind it ~60
QTY_PATTERN = re.compile(r"(\d+)\s*$")  # the "x" often reads as "%" or vanishes; the digits are reliable
LENGTH_PATTERN = re.compile(r"(\d+)\s*FT", re.I)

_templates: dict = {}
_library: list | None = None


def _template(name: str, scale: float):
    key = (name, round(scale, 3))
    if key not in _templates:
        t = cv2.imread(str(TEMPLATE_DIR / f"{name}.png"), cv2.IMREAD_GRAYSCALE)
        if scale != 1:
            t = cv2.resize(t, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        _templates[key] = t
    return _templates[key]


def _find(gray, name, scale, region=None):
    t = _template(name, scale)
    x0, y0 = 0, 0
    if region is not None:
        x0, y0, x1, y1 = region
        gray = gray[max(y0, 0):y1, max(x0, 0):x1]
        x0, y0 = max(x0, 0), max(y0, 0)
    if gray.shape[0] < t.shape[0] or gray.shape[1] < t.shape[1]:
        return None
    _, score, _, (x, y) = cv2.minMaxLoc(cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED))
    return (x0 + x, y0 + y, score) if score >= ANCHOR_MIN else None


def _ocr(crop, threshold=None, config="--psm 7") -> str:
    if crop.size == 0 or not _tesseract_ready():
        return ""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    if threshold is None:
        _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        _, ink = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
    return pytesseract.image_to_string(ink, config=config).strip()


def _read_short_qty(crop) -> str:
    """A short quantity ("x2") that the line read missed: larger, the left third dropped (the icon can poke into the
    box there), a white margin, and only the characters a quantity can have."""
    if crop.size == 0 or not _tesseract_ready():
        return ""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    big = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    _, ink = cv2.threshold(big, QTY_TEXT, 255, cv2.THRESH_BINARY_INV)
    ink = cv2.copyMakeBorder(ink[:, ink.shape[1] // 3:], 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return pytesseract.image_to_string(ink, config="--psm 7 -c tessedit_char_whitelist=x0123456789ft").strip()


def _icon_key(icon) -> np.ndarray:
    return cv2.resize(icon, (64, 44), interpolation=cv2.INTER_AREA).astype(np.float32)


def _load_library() -> list:
    global _library
    if _library is None:
        _library = []
        if LIBRARY_DIR.exists():
            for folder in sorted(p for p in LIBRARY_DIR.iterdir() if p.is_dir() and not p.name.startswith("_")):
                for f in sorted(folder.glob("*.png")):
                    img = cv2.imread(str(f))
                    if img is not None:
                        _library.append((folder.name, _icon_key(img)))
    return _library


def reload_library():
    global _library
    _library = None


def identify(icon) -> tuple[str | None, float]:
    """The library item this icon looks most like, and how alike (None when nothing is close enough)."""
    key = _icon_key(icon)
    best, best_score = None, -1.0
    for item, ref in _load_library():
        score = float(cv2.matchTemplate(key, ref, cv2.TM_CCOEFF_NORMED)[0][0])
        if score > best_score:
            best, best_score = item, score
    return (best if best_score >= ITEM_MATCH else None), best_score


def _slot_used(image, sx, sy, scale) -> bool:
    """A used slot is a lighter square: its left edge steps up in brightness (17-47 grey levels); an empty position
    shows no step at all."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    y0, y1 = sy + int(20 * scale), sy + int(160 * scale)
    inside = float(gray[y0:y1, sx + int(3 * scale):sx + int(8 * scale)].mean())
    outside = float(gray[y0:y1, sx - int(10 * scale):sx - int(5 * scale)].mean())
    return inside - outside > 8


def offer_kind(text: str) -> str:
    t = text.lower()
    if "rare mood" in t or "over the odds" in t:
        return "rare"
    if "forget that" in t or "how about this" in t:
        return "next"
    if "will do nicely" in t or "here's what" in t or "here is what" in t or "give you for the lot" in t:
        return "first"
    return "other"


REFUSAL_WORDS = ("today", "your loss")  # "...not offering on this today", with a "Your loss" option to click


def read_dialogue(image: np.ndarray) -> str | None:
    """The Stablehand's lines and options when his dialogue box is up (with or without a Sale panel), else None."""
    h, w = image.shape[:2]
    scale = w / BASE_WIDTH
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    header = _find(gray, "stablehand", scale, (int(w * 0.5), int(h * 0.2), int(w * 0.95), int(h * 0.6)))
    if header is None:
        return None
    hx, hy, _ = header
    S = lambda v: int(round(v * scale))  # noqa: E731
    return " ".join(_ocr(image[hy + S(70):hy + S(390), hx + S(35):hx + S(935)], config="--psm 6").split())


def is_refusal(text: str | None) -> bool:
    return bool(text) and any(w in text.lower() for w in REFUSAL_WORDS)


def read_sale(image: np.ndarray) -> dict:
    """{"found": False} unless a Sale panel is showing; otherwise its name, dialogue, offer kind and items."""
    h, w = image.shape[:2]
    scale = w / BASE_WIDTH
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    anchor = _find(gray, "rewards", scale, (int(w * 0.5), int(h * 0.3), int(w * 0.95), int(h * 0.85)))
    if anchor is None:
        return {"found": False}
    ax, ay, _ = anchor
    S = lambda v: int(round(v * scale))  # noqa: E731

    nx, ny, nw, nh = (S(v) for v in NAME_BOX)
    name = _ocr(image[ay + ny:ay + ny + nh, ax + nx:ax + nx + nw])
    name = re.sub(r"[^A-Za-z0-9 '\-]", "", name).strip()

    dialogue = ""
    header = _find(gray, "stablehand", scale, (ax - S(200), ay - S(700), ax + S(400), ay - S(300)))
    if header is not None:
        hx, hy, _ = header
        dx, dy, dw, dh = (S(v) for v in DIALOGUE_BELOW_HEADER)
        dialogue = " ".join(_ocr(image[hy + dy:hy + dy + dh, hx + dx:hx + dx + dw], config="--psm 6").split())

    items = []
    for k in range(3):
        sx = ax + S(SLOT_FIRST[0] + k * SLOT_STEP)
        sy = ay + S(SLOT_FIRST[1])
        slot = image[sy:sy + S(SLOT_SIZE), sx:sx + S(SLOT_SIZE)]
        if slot.size == 0 or not _slot_used(image, sx, sy, scale):
            break
        ix, iy, iw, ih = (S(v) for v in ICON_BOX)
        icon = slot[iy:iy + ih, ix:ix + iw]
        qx, qy, qw, qh = (S(v) for v in QTY_BOX)
        qty_text = _ocr(slot[qy:qy + qh, qx:qx + qw], threshold=QTY_TEXT,
                        config="--psm 7")
        length = LENGTH_PATTERN.search(qty_text)
        m = None if length else QTY_PATTERN.search(qty_text)
        if not length and not m and qty_text:
            # Text there but no number ("x2" read as "a?"): read it again more carefully. No text at all is a single
            # item, which has no quantity label - a retry there only reads noise (a door became 7).
            again = _read_short_qty(slot[qy:qy + qh, qx:qx + qw])
            m = re.search(r"x(\d+)$", again)  # only with its "x": anything else is noise
        item, score = identify(icon)
        items.append({"item": item, "match": round(score, 3), "amount": int(m.group(1)) if m else 1,
                      "length_ft": int(length.group(1)) if length else None, "icon": icon})
    wool = re.match(r"^(\d+)\s*Wool", name, re.I)
    return {"found": True, "name": name, "wool": int(wool.group(1)) if wool else None, "dialogue": dialogue,
            "kind": offer_kind(dialogue), "items": items,
            "scrap": sum(i["amount"] for i in items if i["item"] == "scrap")}
