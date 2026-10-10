"""Old room rule vs pair mode (run: python sim_pairs.py LYFH 40 6 - target, runs, founders): time to the first god animal (Good/Good on every target gene).

Each run starts from the same random founders. Every 5 minutes the planner is asked for a plan and the player follows
it at once: animals go where it says, anything sold/culled/rejected leaves. In a breeding room a free grown ram and a
free grown ewe mate straight away. Gestation 10 min, growth 60, ewe rest 41/66/101 and ram rest 6/10/15 by shown F.
Planner sees both rows (test-server mode) so both rules get the same information.
"""
import random
import statistics
import sys
from types import SimpleNamespace

import pools

TARGET = sys.argv[1] if len(sys.argv) > 1 else "LYFH"
RUNS = int(sys.argv[2]) if len(sys.argv) > 2 else 40
FOUNDERS = int(sys.argv[3]) if len(sys.argv) > 3 else 6
STEP, LIMIT = 5.0, 60 * 72.0
GENES = "DLYFH"
RANK = "BOG"
EWE_REST = {"G": 41, "O": 66, "B": 101}
RAM_REST = {"G": 6.25, "O": 10, "B": 15.4}
HAREMS = ["VIP Suite", "VIP 2"]


def animal(i, sex, a, b, t):
    top = "".join(max(x, y, key=RANK.index) for x, y in zip(a, b))
    bottom = "".join(min(x, y, key=RANK.index) for x, y in zip(a, b))
    return SimpleNamespace(id=i, name=f"a{i}", code=f"S{i}", sex=sex, genes_top=top, genes_bottom=bottom, copies=(a, b),
                           born=t, pen="Ladies" if sex == "F" else "Gentlemen", free=t, pregnant_until=None, mate=None,
                           is_lamb=False)


def god(a):
    return all(a.genes_top[GENES.index(g)] == "G" and a.genes_bottom[GENES.index(g)] == "G" for g in TARGET)


def run(seed, pair_mode):
    pools.PAIR_MODE = pair_mode
    rng = random.Random(seed)
    herd = [animal(i, "MF"[i % 2], "".join(rng.choice("GOB") for _ in GENES), "".join(rng.choice("GOB") for _ in GENES), -60)
            for i in range(FOUNDERS)]
    next_id, t, previous = FOUNDERS, 0.0, set()
    while t < LIMIT:
        for a in herd:
            a.is_lamb = t - a.born < 60
        # births
        for ewe in [a for a in herd if a.pregnant_until is not None and a.pregnant_until <= t]:
            ram = ewe.mate
            child = tuple("".join(rng.choice(c) for c in zip(*pair)) for pair in (ewe.copies, ram.copies))
            lamb = animal(next_id, rng.choice("MF"), child[0], child[1], t)
            lamb.pen = ewe.pen
            next_id += 1
            herd.append(lamb)
            if god(lamb):
                return t
            ewe.pregnant_until, ewe.free = None, t + EWE_REST[ewe.genes_top[3]]
        plan = pools.arrange(herd, TARGET, None, HAREMS, ["Gentlemen", "Ladies", "Rejects"], 1, 9,
                             previous=previous, harem_sizes={h: 1 for h in HAREMS},
                             holding_by_sex={"M": "Gentlemen", "F": "Ladies"}, reject_room="Rejects")
        previous = {r["ram"] for r in plan["harems"].values() if r["ram"]} | \
                   {int(k) for k, v in plan["verdicts"].items() if v["verdict"] == "promote"}
        gone = {int(k) for k, v in plan["verdicts"].items() if v["verdict"] in ("sell", "cull", "reject")}
        herd = [a for a in herd if a.id not in gone or a.pregnant_until is not None]  # pregnant ewes sell after
        for a in herd:
            a.pen = plan["pen"].get(a.id, a.pen)
        # matings: a free grown ram with a free grown ewe in the same breeding room
        for room in HAREMS:
            here = [a for a in herd if a.pen == room and not a.is_lamb]
            rams = [a for a in here if a.sex == "M" and a.free <= t]
            if any(a.is_lamb for a in herd if a.pen == room):
                continue  # rams wait while lambs are in the room
            for ewe in (a for a in here if a.sex == "F" and a.free <= t and a.pregnant_until is None):
                if rams:
                    ram = rams.pop()
                    ewe.pregnant_until, ewe.mate = t + 10, ram
                    ram.free = t + RAM_REST[ram.genes_top[3]]
        t += STEP
    return LIMIT


if __name__ == '__main__':
  for mode in (False, True):
    times = [run(seed, mode) for seed in range(RUNS)]
    done = [x for x in times if x < LIMIT]
    print(f"{'pair mode' if mode else 'old rule '}: median {statistics.median(times) / 60:.1f} h, "
          f"mean {statistics.mean(times) / 60:.1f} h, reached in {len(done)}/{RUNS} runs (cap {LIMIT / 60:.0f} h)")
