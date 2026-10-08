"""Build the vendor item icon library from sales already labelled by hand.

Each labelled sale event notes its offers ("1 = 620 metal fragments + horse saddle + 65 scrap; 2 = ...") and the
captures they came from ("[captures 66-68]"). Every capture's panel is read, paired with the labelled offer whose
quantities it shows, and its icons are saved under vendor_items/<item>/. Run: python build_vendor_library.py
"""
import re
import shutil
import sqlite3

import cv2

import vendor_reader
from config import CAPTURE_DIR, DB_PATH

# Labels as written in the notes -> item names in the library.
ITEM_NAMES = [
    (r"incendiary pistol bullets?", "incendiary_pistol_bullets"),
    (r"pistol bullets?", "pistol_bullets"),
    (r"5\.56( rifle ammo)?", "rifle_ammo_556"),
    (r"metal frag(ment)?s?", "metal_fragments"),
    (r"hqm ore", "hqm_ore"),
    (r"gunpowder", "gunpowder"),
    (r"gears?", "gears"),
    (r"scrap", "scrap"),
    (r"horse saddle", "horse_saddle"),
    (r"cctv cameras?", "cctv_camera"),
    (r"targeting computers?", "targeting_computer"),
    (r"blueprint fragments?", "blueprint_fragment"),
    (r"rifle bod(y|ies)", "rifle_body"),
    (r"smg bod(y|ies)", "smg_body"),
    (r"rifle \(semi-auto\?\)|rifle", "rifle"),
    (r"rope", "rope"),
    (r"tarps?", "tarp"),
    (r"blue keycard", "blue_keycard"),
    (r"(high caliber |python )?revolver", "high_caliber_revolver"),
    (r"pressure pad", "pressure_pad"),
]


def parse_item(text: str):
    text = text.strip().lower()
    text = re.sub(r"\s*\((one item only|no scrap|taken[^)]*)\)", "", text)
    length = re.search(r"\((\d+)\s*ft\)", text)
    m = re.match(r"^(\d+)\s+(.*)$", text)
    amount, rest = (int(m.group(1)), m.group(2)) if m else (1, text)
    for pattern, name in ITEM_NAMES:
        if re.match(pattern, rest):
            return name, (f"{length.group(1)}ft" if length else amount)
    return None, amount


def parse_offers(notes: str) -> list[list]:
    body = notes.split("[")[0]
    parts = re.split(r"\b([123]) = ", body)
    offers = []
    for i in range(1, len(parts) - 1, 2):
        text = re.split(r";\s*$", parts[i + 1].strip())[0].rstrip(";").strip()
        offers.append([parse_item(x) for x in text.split(" + ") if x.strip()])
    if not offers and ":" in body:  # "offer 1 taken (only one captured): 17 pistol bullets + blue keycard, no scrap"
        text = body.split(":", 1)[1].split(",")[0]
        offers.append([parse_item(x) for x in text.split(" + ")])
    return offers


def capture_ids(notes: str) -> list[int]:
    m = re.search(r"\[captures? ([\d\-, ]+)\]", notes)
    if not m:
        return []
    ids = []
    for part in m.group(1).split(","):
        a, _, b = part.strip().partition("-")
        ids += list(range(int(a), int(b or a) + 1))
    return ids


def main():
    if vendor_reader.LIBRARY_DIR.exists():
        shutil.rmtree(vendor_reader.LIBRARY_DIR)
    db = sqlite3.connect(DB_PATH)
    saved = skipped = 0
    for notes, in db.execute("select notes from event where notes like '%[capture%' and notes like '%=%' "
                             "or notes like '%only one captured%'"):
        offers = parse_offers(notes)
        for cid in capture_ids(notes):
            row = db.execute("select path from capture where id = ?", (cid,)).fetchone()
            image = cv2.imread(str(CAPTURE_DIR / row[0])) if row else None
            reading = vendor_reader.read_sale(image) if image is not None else {"found": False}
            if not reading["found"]:
                skipped += 1
                continue
            seen = [f"{i['length_ft']}ft" if i["length_ft"] else i["amount"] for i in reading["items"]]
            match = next((o for o in offers if [a for _, a in o] == seen and all(n for n, _ in o)), None)
            if match is None:
                skipped += 1
                continue
            for k, ((name, _), item) in enumerate(zip(match, reading["items"])):
                folder = vendor_reader.LIBRARY_DIR / name
                folder.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(folder / f"{cid}_{k}.png"), item["icon"])
                saved += 1
    print(f"saved {saved} icons; {skipped} captures skipped")
    for folder in sorted(vendor_reader.LIBRARY_DIR.iterdir()):
        print(f"  {folder.name}: {len(list(folder.glob('*.png')))}")


if __name__ == "__main__":
    main()
