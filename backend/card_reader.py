"""Reads an animal's status card out of a full-screen capture.

The card is anchored on its "GENETICS" label: the label is always at the same x for a given resolution, and
everything else on the card sits at a fixed offset from it. Only the card's y changes, because the card is centred
vertically and its height depends on which lines it shows.

Gene circles are classified by the colour of their ring (the letter in the middle is white). Lineage markers are
read digit by digit against glyphs learned from confirmed captures, since marker colours repeat between numbers.

Offsets were measured on 3840x2160 captures and scale with the frame width.
"""
from pathlib import Path

import re
import shutil

import cv2
import numpy as np

from config import DATA_DIR

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


NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z '-]{0,38}$")
NAME_MIN_CONFIDENCE = 75
WINDOWS_TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


def _tesseract_ready() -> bool:
    if pytesseract is None:
        return False
    if shutil.which("tesseract"):
        return True
    if WINDOWS_TESSERACT.exists():
        pytesseract.pytesseract.tesseract_cmd = str(WINDOWS_TESSERACT)
        return True
    return False


def read_name(image: np.ndarray, box: list[float]) -> str | None:
    """The animal's name as text, but only when it reads cleanly as Latin letters.

    Names can be in any script. Turning a Cyrillic or Chinese name into Latin letters wouldn't help anyone match it
    in game, so anything that isn't a confident Latin read comes back as None and the app uses its own ID instead.
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
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)  # dark text on white
    data = pytesseract.image_to_data(ink, config="--psm 7", output_type=pytesseract.Output.DICT)
    words = [(t, float(c)) for t, c in zip(data["text"], data["conf"]) if t.strip() and float(c) >= 0]
    if not words:
        return None
    text = " ".join(t for t, _ in words).strip()
    confidence = min(c for _, c in words)
    if confidence < NAME_MIN_CONFIDENCE or not NAME_PATTERN.match(text):
        return None
    return text


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
        "name": read_name(image, name_box),
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
