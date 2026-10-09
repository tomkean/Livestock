"""Reads an animal's status card out of a full-screen capture.

The card is anchored on its "GENETICS" label: the label is always at the same x for a given resolution, and
everything else on the card sits at a fixed offset from it. Only the card's y changes, because the card is centred
vertically and its height depends on which lines it shows.

Gene circles are classified by the colour of their ring (the letter in the middle is white). Lineage markers are
read digit by digit against glyphs learned from confirmed captures, since marker colours repeat between numbers.

Offsets were measured on 3840x2160 captures and scale with the frame width.
"""
from pathlib import Path

import os
import re
import shutil

import cv2
import numpy as np

from config import DATA_DIR, TESSDATA_DIR

try:
    import pytesseract
except ImportError:  # optional: without it, names fall back to the app's ID
    pytesseract = None

REF_WIDTH = 3840
TEMPLATE_DIR = Path(__file__).resolve().parent / "card_templates"
SEED_DIGITS = TEMPLATE_DIR / "digits"  # shipped with the repo
LEARNED_DIGITS = DATA_DIR / "digits"  # added as captures are confirmed

ANCHOR_MIN_SCORE = 0.8

# Offsets from the top-left of the "GENETICS" label, at REF_WIDTH.
COLUMNS_DX = (320, 388, 457, 525, 593)  # D L Y F H
MARKER_DX = 661
TOP_DY, BOTTOM_DY = 30, 80
TOP_RADIUS, BOTTOM_RADIUS = 27, 16
INBRED_BOX = (0, 45, 150, 35)  # x, y, w, h of the red "INBRED" label under GENETICS
NAME_BOX = (115, -125, 525, 60)
CARD_LEFT, CARD_TOP, CARD_RIGHT = -25, -157, 725
CARD_CENTRE_Y = 862  # the card is centred on this y; its bottom mirrors its top about it

DIGIT_SIZE = (16, 24)  # w, h every glyph is normalised to


def _anchor_template():
    return cv2.imread(str(TEMPLATE_DIR / "genetics.png"), cv2.IMREAD_GRAYSCALE)


def find_anchor(image: np.ndarray) -> tuple[int, int, float, float] | None:
    """Top-left of the GENETICS label as (x, y, scale, score), or None if no card is showing."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    base = _anchor_template()
    scale = image.shape[1] / REF_WIDTH
    tpl = base if scale == 1 else cv2.resize(base, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    if tpl.shape[0] >= gray.shape[0] or tpl.shape[1] >= gray.shape[1]:
        return None
    _, score, _, (x, y) = cv2.minMaxLoc(cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED))
    if score < ANCHOR_MIN_SCORE:
        return None
    return x, y, scale, float(score)


def _ring_colour(image, cx, cy, radius) -> np.ndarray:
    """Median BGR of the circle's ring, between the white letter and the edge."""
    h, w = image.shape[:2]
    yy, xx = np.ogrid[:h, :w]
    d2 = (xx - cx) ** 2 + (yy - cy) ** 2
    ring = (d2 >= (0.62 * radius) ** 2) & (d2 <= (0.85 * radius) ** 2)
    return np.median(image[ring], axis=0)


def classify_gene(bgr) -> str:
    """G(ood, green), O(k, grey) or B(ad, red); '?' when the colour is none of them."""
    b, g, r = (float(v) for v in bgr)
    if g - r > 25 and g - b > 25:
        return "G"
    if r - g > 40 and r - b > 25:
        return "B"
    if max(b, g, r) - min(b, g, r) < 30 and 80 < (b + g + r) / 3 < 220:
        return "O"
    return "?"


def _glyphs(disc: np.ndarray) -> list[np.ndarray]:
    """The white digit shapes inside a marker disc, left to right, each normalised to DIGIT_SIZE."""
    gray = cv2.cvtColor(disc, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(disc, cv2.COLOR_BGR2HSV)
    # White text: bright and unsaturated. The disc behind it is saturated.
    mask = ((gray > 170) & (hsv[:, :, 1] < 70)).astype(np.uint8)
    h, w = mask.shape
    yy, xx = np.ogrid[:h, :w]
    inside = ((xx - w / 2) ** 2 + (yy - h / 2) ** 2) <= (0.8 * min(h, w) / 2) ** 2
    mask &= inside.astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    parts = []
    for i in range(1, n):
        x, y, cw, ch, area = stats[i]
        if ch < 0.3 * h or area < 6:
            continue
        glyph = mask[y:y + ch, x:x + cw] * 255
        parts.append((x, cv2.resize(glyph, DIGIT_SIZE, interpolation=cv2.INTER_AREA)))
    return [g for _, g in sorted(parts, key=lambda p: p[0])]


def _digit_library() -> dict[str, list[np.ndarray]]:
    library: dict[str, list[np.ndarray]] = {}
    for root in (SEED_DIGITS, LEARNED_DIGITS):
        if not root.exists():
            continue
        for f in root.glob("*/*.png"):
            img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                library.setdefault(f.parent.name, []).append(img.astype(np.float32))
    return library


def _match_digit(glyph: np.ndarray, library) -> tuple[str | None, float]:
    g = glyph.astype(np.float32)
    best, best_score = None, -1.0
    for digit, samples in library.items():
        for s in samples:
            score = float(cv2.matchTemplate(g, s, cv2.TM_CCOEFF_NORMED)[0, 0])
            if score > best_score:
                best, best_score = digit, score
    return best, best_score


def _marker_disc(image, cx, cy, radius):
    return image[max(cy - radius, 0):cy + radius, max(cx - radius, 0):cx + radius]


def read_marker(image, cx, cy, radius, library) -> int | None:
    glyphs = _glyphs(_marker_disc(image, cx, cy, radius))
    if not glyphs or len(glyphs) > 2:
        return None
    digits = []
    for g in glyphs:
        digit, score = _match_digit(g, library)
        # Measured on the first 11 captures: correct matches scored >= 0.73, digits never seen before <= 0.63.
        if digit is None or score < 0.7:
            return None
        digits.append(digit)
    return int("".join(digits))


def _layout(anchor):
    x, y, s, _ = anchor
    p = lambda dx, dy: (int(round(x + dx * s)), int(round(y + dy * s)))
    return {
        "top": [p(dx, TOP_DY) for dx in COLUMNS_DX],
        "bottom": [p(dx, BOTTOM_DY) for dx in COLUMNS_DX],
        "marker_top": p(MARKER_DX, TOP_DY),
        "marker_bottom": p(MARKER_DX, BOTTOM_DY),
        "top_r": int(round(TOP_RADIUS * s)),
        "bottom_r": int(round(BOTTOM_RADIUS * s)),
    }


AGE_BOX = (400, 150, 300, 45)  # x, y, w, h of the AGE value ("9 MINUTES") from the anchor
AGE_PATTERN = re.compile(r"(\d+)\s*(SECOND|MINUTE|HOUR|DAY)S?")
AGE_UNIT_MINUTES = {"SECOND": 1 / 60, "MINUTE": 1, "HOUR": 60, "DAY": 1440}
AGE_THRESHOLDS = (110, 140, 170)  # one threshold alone misreads digits ("52" as "92"), so read at several and vote
LAMB_MAX_AGE = 60  # minutes: a lamb grows up at 60, so a lamb card never shows more
NAME_PATTERN = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9 '-]{0,38}$")  # digits for "Jay the 3rd"
CYRILLIC = re.compile(r"[А-Яа-яЁё]")
# Russian names, read in Cyrillic and kept in Latin letters (Станислав -> Stanislav, Снежана -> Snezhana), so they can be
# typed and matched like any other name.
_LATIN = dict(zip("абвгдезийклмнопрстуфыэ", "abvgdeziyklmnoprstufye")) | {
    "ё": "e", "ж": "zh", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ь": "", "ю": "yu", "я": "ya"}
# Russian first names ending in -a or -ya that are male; otherwise those endings are female and the rest male.
RUSSIAN_MALE_A = {"никита", "илья", "кузьма", "фома", "савва", "лука", "данила", "гаврила", "миша", "саша", "паша",
                  "гоша", "дима", "ваня", "петя", "коля", "толя", "серёжа", "сережа", "лёша", "леша", "вова", "слава"}
NAME_MIN_CONFIDENCE = 75
PREGNANT_SUFFIX = re.compile(r"\s+pregnant$", re.I)
WINDOWS_TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


def _name_languages() -> str:
    return "eng+rus" if (TESSDATA_DIR / "rus.traineddata").exists() else "eng"


def to_latin(text: str) -> str:
    """Cyrillic letters to Latin ones, keeping capitals; anything else is left as it is."""
    out = []
    for ch in text:
        latin = _LATIN.get(ch.lower())
        out.append(ch if latin is None else latin.capitalize() if ch.isupper() else latin)
    return "".join(out)


def russian_sex(name: str) -> str | None:
    """Sex from a Russian first name in Cyrillic: -a/-ya endings are female, apart from a few male names."""
    first = name.strip().split()[0].lower() if name.strip() else ""
    if not CYRILLIC.search(first):
        return None
    if first in RUSSIAN_MALE_A:
        return "M"
    return "F" if first[-1] in "ая" else "M"


def _tesseract_ready() -> bool:
    if pytesseract is None:
        return False
    if _name_languages() != "eng":
        os.environ.setdefault("TESSDATA_PREFIX", str(TESSDATA_DIR))
    if shutil.which("tesseract"):
        return True
    if WINDOWS_TESSERACT.exists():
        pytesseract.pytesseract.tesseract_cmd = str(WINDOWS_TESSERACT)
        return True
    return False


def read_name(image: np.ndarray, box: list[float]) -> str | None:
    """The animal's name as text, but only when it reads cleanly, in Latin or (with the rus language file) Cyrillic.

    Names can be in any script. Anything else (Chinese, say) that isn't a confident read comes back as None, and the
    app uses its own ID instead. read_card turns Cyrillic into Latin letters.
    """
    if not _tesseract_ready():
        return None
    h, w = image.shape[:2]
    x, y, bw, bh = box
    crop = image[int(y * h):int((y + bh) * h), int(x * w):int((x + bw) * w)]
    if crop.size == 0:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    # The name is light grey on the card's dark header. A fixed threshold read all of the first 14 captures;
    # Otsu's automatic one failed when bright scenery showed through behind the name, so it is only a fallback.
    _, fixed = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY_INV)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    for ink in (fixed, otsu):
        data = pytesseract.image_to_data(ink, lang=_name_languages(), config="--psm 7",
                                         output_type=pytesseract.Output.DICT)
        words = [(t, float(c)) for t, c in zip(data["text"], data["conf"]) if t.strip() and float(c) >= 0]
        if not words:
            continue
        text = " ".join(t for t, _ in words).strip()
        if min(c for _, c in words) >= NAME_MIN_CONFIDENCE and NAME_PATTERN.match(text):
            return text
    return None


def read_age(image: np.ndarray, anchor, max_minutes: float | None = None) -> float | None:
    """The animal's age in minutes from the card's AGE line ("1 MINUTE", "9 MINUTES", "2 HOURS")."""
    if not _tesseract_ready():
        return None
    x, y, s, _ = anchor
    ax, ay, aw, ah = (int(round(v * s)) for v in AGE_BOX)
    crop = image[y + ay:y + ay + ah, x + ax:x + ax + aw]
    if crop.size == 0:
        return None
    gray = cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    ages = []
    for threshold in AGE_THRESHOLDS:
        _, ink = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
        text = pytesseract.image_to_string(
            ink, config="--psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ").upper()
        match = AGE_PATTERN.search(text.replace("O", "0").replace("0NE", "1") if not re.search(r"\d", text) else text)
        if match:
            age = int(match.group(1)) * AGE_UNIT_MINUTES[match.group(2)]
            if max_minutes is None or age <= max_minutes:
                ages.append(age)
    if not ages:
        return None
    return max(ages, key=ages.count)  # the most common reading; on a tie, the first


try:
    import gender_guesser.detector as _gender
    _GENDER = _gender.Detector(case_sensitive=False)
except ImportError:  # optional: without it lambs just stay unsexed until their horns show
    _GENDER = None


# Names given to both sexes; the dictionary is sure about some of them, the herd says otherwise (Jessie and Taylor: rams).
EITHER_SEX = {"jessie", "jesse", "taylor", "jamie", "jordan", "casey", "alex", "sam", "robin", "terry", "kelly",
              "courtney", "aubrey", "morgan", "riley", "jody", "leslie", "lee", "kim", "chris", "pat", "drew"}


def sex_from_name(name: str | None) -> str | None:
    """Sex suggested by an English first name. The game names animals by sex: 58 of 60 sexed sheep matched, the two
    misses unisex names (Jessie, Courtney). Only clearly male or female names count; anything else is None."""
    if not name or _GENDER is None:
        return None
    first = name.strip().split()[0]
    if first.lower() in EITHER_SEX:
        return None
    # Rust's names look American; the blended world list calls Laurence female (French usage) where the US list says
    # male. The world list fills in where the US list isn't sure, unless the US list leans the other way.
    us, world = _GENDER.get_gender(first, "usa"), _GENDER.get_gender(first)
    if us in ("male", "female"):
        return "M" if us == "male" else "F"
    if world in ("male", "female") and us != f"mostly_{'female' if world == 'male' else 'male'}":
        return "M" if world == "male" else "F"
    return None


# The YIELD line sits under AGE: "16 Wool per 3 minutes". White text over a part-filled light bar, so only the
# near-white pixels are text.
YIELD_BOX = (380, 213, 380, 48)  # x, y, w, h of the YIELD value from the anchor
YIELD_PATTERN = re.compile(r"(\d+)\s*([A-Z]+)\s*PER\s*(\d+)\s*(SEC|MIN|HOU)")  # "16 Wool per 3 minutes", "1 Milk per 5 minutes"
YIELD_UNIT_MINUTES = {"SEC": 1 / 60, "MIN": 1, "HOU": 60}
YIELD_TEXT = 225  # grey level: text is near-white, the bar behind it light grey


def read_yield(image: np.ndarray, anchor) -> dict | None:
    """Wool (or milk) per period from the YIELD line, as {"amount", "minutes", "per_hour"}."""
    if not _tesseract_ready():
        return None
    x, y, s, _ = anchor
    bx, by, bw, bh = (int(round(v * s)) for v in YIELD_BOX)
    crop = image[y + by:y + by + bh, x + bx:x + bx + bw]
    if crop.size == 0:
        return None
    gray = cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, ink = cv2.threshold(gray, YIELD_TEXT, 255, cv2.THRESH_BINARY_INV)
    text = pytesseract.image_to_string(ink, config="--psm 7").upper()
    match = YIELD_PATTERN.search(text)
    if not match:
        return None
    amount, period = int(match.group(1)), int(match.group(3)) * YIELD_UNIT_MINUTES[match.group(4)]
    if not period:
        return None
    return {"amount": amount, "product": match.group(2).lower(), "minutes": period,
            "per_hour": round(amount * 60 / period, 1)}


# Conditions: located by the "CONDITIONS" heading (its height on the card depends on which lines sit above it), then
# each bar's filled length is read along a thin band under the text. Matched the printed values within ~1 point.
CONDITION_SEARCH = (0, 200, 260, 800)  # x, y, w, h below the anchor to look for the heading
CONDITION_ROWS = {"food": 70, "water": 135, "personal_space": 200, "overall": 262}  # bar centre below the heading
BAR_X = (384, 710)  # bar start and end, from the anchor
BAR_BAND = (20, 26)  # rows below each bar's centre: below the printed number
BAR_FILLED = 110  # grey level: the filled part of a bar is light, the empty part dark


def read_conditions(image: np.ndarray, anchor) -> dict | None:
    """Food, water, personal space and overall as percentages, measured from the bars."""
    tpl = cv2.imread(str(TEMPLATE_DIR / "conditions.png"), cv2.IMREAD_GRAYSCALE)
    x, y, s, _ = anchor
    if s != 1:
        tpl = cv2.resize(tpl, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    sx, sy, sw, sh = (int(round(v * s)) for v in CONDITION_SEARCH)
    region = cv2.cvtColor(image[y + sy:y + sy + sh, x + sx:x + sx + sw], cv2.COLOR_BGR2GRAY)
    if region.shape[0] < tpl.shape[0] or region.shape[1] < tpl.shape[1]:
        return None
    _, score, _, (_, hy) = cv2.minMaxLoc(cv2.matchTemplate(region, tpl, cv2.TM_CCOEFF_NORMED))
    if score < 0.7:
        return None
    top = y + sy + hy
    b0, b1 = (int(round(v * s)) for v in BAR_BAND)
    x0, x1 = (int(round(v * s)) for v in BAR_X)
    out = {}
    for name, dy in CONDITION_ROWS.items():
        row = top + int(round(dy * s))
        band = image[row + b0:row + b1, x + x0:x + x1]
        if band.size == 0:
            return None
        out[name] = round(100 * float((cv2.cvtColor(band, cv2.COLOR_BGR2GRAY).mean(axis=0) > BAR_FILLED).mean()))
    return out


PORTRAIT_BOX = (-10, -140, 110, 110)  # x, y, w, h of the card's portrait from the anchor
LAMB_MAX_SCORE = 0.9  # adult portraits matched the adult template at >= 0.98, lambs at <= 0.75


# Every adult of a species shares one portrait; a cow's scored 0.14 against the sheep's.
ADULT_PORTRAITS = {"sheep": "adult_portrait.png", "cow": "adult_portrait_cow.png"}


def adult_species(image: np.ndarray, anchor) -> str | None:
    """The species whose adult portrait the card shows, or None (a lamb or calf, or no portrait found)."""
    x, y, s, _ = anchor
    px, py, pw, ph = (int(round(v * s)) for v in PORTRAIT_BOX)
    crop = image[max(y + py, 0):y + py + ph, max(x + px, 0):x + px + pw]
    if crop.size == 0:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    best, best_score = None, LAMB_MAX_SCORE
    for species, name in ADULT_PORTRAITS.items():
        tpl = cv2.imread(str(TEMPLATE_DIR / name), cv2.IMREAD_GRAYSCALE)
        if s != 1:
            tpl = cv2.resize(tpl, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        tpl = tpl[5:-5, 5:-5]
        if gray.shape[0] < tpl.shape[0] or gray.shape[1] < tpl.shape[1]:
            continue
        score = float(cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED).max())
        if score >= best_score:
            best, best_score = species, score
    return best


def is_lamb(image: np.ndarray, anchor) -> bool:
    """Lambs have their own portrait; every adult of a species shares one."""
    return adult_species(image, anchor) is None


def read_card(image: np.ndarray) -> dict:
    """Everything the card shows that can be read reliably. Unreadable values come back as '?' or None."""
    anchor = find_anchor(image)
    if anchor is None:
        return {"found": False}
    x, y, s, score = anchor
    h, w = image.shape[:2]
    lay = _layout(anchor)
    library = _digit_library()

    genes_top = "".join(classify_gene(_ring_colour(image, cx, cy, lay["top_r"])) for cx, cy in lay["top"])
    # The second row is only drawn when the server shows both copies (livestock.panelalleles).
    bottom = [classify_gene(_ring_colour(image, cx, cy, lay["bottom_r"])) for cx, cy in lay["bottom"]]
    genes_bottom = "".join(bottom) if bottom.count("?") <= 1 else None

    herd_top = read_marker(image, *lay["marker_top"], lay["top_r"], library)
    herd_bottom = read_marker(image, *lay["marker_bottom"], lay["bottom_r"], library) if genes_bottom else None

    ix, iy, iw, ih = (int(round(v * s)) for v in INBRED_BOX)
    label = image[y + iy:y + iy + ih, x + ix:x + ix + iw].astype(int)
    red = (label[:, :, 2] - label[:, :, 1] > 60) & (label[:, :, 2] > 120)
    inbred = bool(red.mean() > 0.03)

    def frac_box(left, top, right, bottom):
        left, right = max(left, 0), min(right, w)
        top, bottom = max(top, 0), min(bottom, h)
        return [left / w, top / h, (right - left) / w, (bottom - top) / h]

    card_top = y + CARD_TOP * s
    card_bottom = 2 * CARD_CENTRE_Y * s - card_top
    nx, ny, nw, nh = (v * s for v in NAME_BOX)
    name_box = frac_box(x + nx, y + ny, x + nx + nw, y + ny + nh)
    # A pregnant ewe's card prints "Pregnant" after her name: it's her status, not part of the name.
    raw_name = read_name(image, name_box) or ""
    pregnant = bool(PREGNANT_SUFFIX.search(raw_name))
    native = PREGNANT_SUFFIX.sub("", raw_name).strip()
    name = to_latin(native) or None
    return {
        "found": True,
        "score": round(score, 3),
        "genes_top": genes_top,
        "genes_bottom": genes_bottom,
        "herd_top": herd_top,
        "herd_bottom": herd_bottom,
        "inbred": inbred,
        "card_box": frac_box(x + CARD_LEFT * s, card_top, x + CARD_RIGHT * s, card_bottom),
        "name_box": name_box,
        "name": name,
        "pregnant": pregnant,
        "sex_guess": russian_sex(native) or sex_from_name(name),  # a Cyrillic name follows Russian usage (Nikita: M)
        # The AGE line is only trustworthy on lambs: adult cards have shown "0 SECONDS" and ages far too low.
        "conditions": read_conditions(image, anchor),
        "yield": read_yield(image, anchor),
        "species": (species := adult_species(image, anchor)),  # None for lambs: their portrait isn't known per species
        "lamb": (lamb := species is None),
        "age_minutes": read_age(image, anchor, LAMB_MAX_AGE) if lamb else None,
    }


def learn_markers(image: np.ndarray, herd_top: int | None, herd_bottom: int | None, root: Path = LEARNED_DIGITS) -> int:
    """Store the digit glyphs of confirmed marker numbers, so later cards can be read. Returns glyphs saved."""
    anchor = find_anchor(image)
    if anchor is None:
        return 0
    lay = _layout(anchor)
    saved = 0
    for value, (cx, cy), r in ((herd_top, lay["marker_top"], lay["top_r"]),
                               (herd_bottom, lay["marker_bottom"], lay["bottom_r"])):
        if value is None:
            continue
        glyphs = _glyphs(_marker_disc(image, cx, cy, r))
        text = str(value)
        if len(glyphs) != len(text):
            continue  # segmentation disagrees with the confirmed number; don't learn from it
        for digit, glyph in zip(text, glyphs):
            folder = root / digit
            folder.mkdir(parents=True, exist_ok=True)
            if len(list(folder.glob("*.png"))) >= 12:
                continue  # enough examples of this digit
            cv2.imwrite(str(folder / f"{len(list(folder.glob('*.png'))):03d}.png"), glyph)
            saved += 1
    return saved
