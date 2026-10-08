"""Infer the vendor's scrap value for each item, assuming the three ordinary offers for one sheep (or wool lot) are worth
the same in total: within a visit, a difference in scrap must be paid for by a difference in items."""
import json
import re
import sqlite3
import statistics as st
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, r'C:\Projects\Rust\Livestock\Github\backend')
from build_vendor_library import parse_offers  # noqa: E402

db = sqlite3.connect(r'C:\Projects\Rust\Livestock\data\livestock.db')
visits = []  # each: list of offers; offer = (scrap, {item: amount})


def norm(items):
    out, scrap = defaultdict(float), 0
    for name, amount in items:
        if name is None:
            return None  # an item we can't name: leave this offer out
        if isinstance(amount, str) and amount.endswith("ft"):
            name, amount = "rope (per ft)", int(amount[:-2])
        if name == "scrap":
            scrap += amount
        else:
            out[name] += amount
    return scrap, dict(out)


# Hand-labelled visits (event notes), skipping rare-mood offers and the automatic ones (taken from the offer table).
for (notes,) in db.execute("select notes from event where kind in ('sold','offers_declined') and notes like '%1 = %' "
                           "and notes not like 'auto:%'"):
    body = notes.split("[")[0]
    offers = []
    for k, items in enumerate(parse_offers(notes), start=1):
        if "rare mood" in body and k == 3:
            continue
        o = norm(items)
        if o:
            offers.append(o)
    if len(offers) >= 2:
        visits.append(offers)

# Automatic visits from the offer table.
for (sale,) in db.execute("select distinct sale from offer"):
    offers = []
    for scrap, items, rare in db.execute("select scrap, items, rare from offer where sale=? order by number", (sale,)):
        if rare:
            continue
        o = norm([(i["item"], f"{i['length_ft']}ft" if i.get("length_ft") else i["amount"]) for i in json.loads(items)])
        if o:
            offers.append(o)
    if len(offers) >= 2:
        visits.append(offers)

# The wool lots (recorded only in MECHANICS.md).
W = [[(85, {"pressure pad": 1, "smg body": 1}), (35, {"incendiary pistol bullets": 41, "rifle body": 2}),
      (265, {"gears": 5, "cctv camera": 1})],
     [(295, {"gunpowder": 100, "metal fragments": 200}), (65, {"metal fragments": 500, "rifle body": 2}),
      (280, {"rifle body": 1, "hqm ore": 8})],
     [(15, {"targeting computer": 1, "gunpowder": 220}), (75, {"blueprint fragment": 1, "cctv camera": 1}),
      (155, {"targeting computer": 1, "metal fragments": 60})]]
alias = {"smg_body": "smg body", "rifle_body": "rifle body", "cctv_camera": "cctv camera", "hqm_ore": "hqm ore",
         "metal_fragments": "metal fragments", "targeting_computer": "targeting computer",
         "blueprint_fragment": "blueprint fragment", "incendiary_pistol_bullets": "incendiary pistol bullets",
         "pistol_bullets": "pistol bullets", "rifle_ammo_556": "5.56 rifle ammo", "horse_saddle": "horse saddle",
         "blue_keycard": "blue keycard"}
visits = [[(s, {alias.get(k, k).replace("_", " "): v for k, v in it.items()}) for s, it in v] for v in visits] + W

items = sorted({k for v in visits for _, it in v for k in it})
rows, rhs = [], []
for v in visits:
    for a in range(len(v)):
        for b in range(a + 1, len(v)):
            sa, ia = v[a]
            sb, ib = v[b]
            rows.append([ia.get(k, 0) - ib.get(k, 0) for k in items])
            rhs.append(sb - sa)
A, y = np.array(rows, float), np.array(rhs, float)


def nnls(A, b, iters=20000):
    # projected gradient with per-column scaling (values can't be negative)
    scale = np.maximum(np.abs(A).max(axis=0), 1)
    As = A / scale
    x = np.zeros(As.shape[1])
    lr = 1.0 / np.linalg.norm(As, 2) ** 2
    for _ in range(iters):
        x = np.maximum(0, x - lr * As.T @ (As @ x - b))
    return x / scale


x = nnls(A, y)
res = y - A @ x
count = {k: sum(1 for v in visits for _, it in v if k in it) for k in items}
print(f"{len(visits)} visits, {len(rows)} equations; typical miss per equation +/- {np.sqrt(np.mean(res**2)):.0f} scrap")
print(f"{'item':28s} {'scrap each':>10s}  offers seen in")
for k, val in sorted(zip(items, x), key=lambda t: -t[1] * 1):
    print(f"  {k:26s} {val:10.2f}  {count[k]}")

# How equal are the offers' totals within a visit, once items are valued?
spreads = []
for v in visits:
    totals = [s + sum(x[items.index(k)] * n for k, n in it.items()) for s, it in v]
    spreads.append(max(totals) - min(totals))
print(f"\nwithin-visit spread of offer totals: median {st.median(spreads):.0f}, mean {st.mean(spreads):.0f} scrap")
