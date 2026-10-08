"""Exact logic over the family tree: which hidden copies are still possible, and which records can't all be true.

Each animal starts, gene by gene, with the pairs its top row allows (the top row shows the stronger copy: G allows
GG/GO/GB, O allows OO/OB, B only BB). Then every recorded mother-father-lamb trio removes the pairs no combination of the
other two could explain, in every direction, and this repeats until nothing changes (a fixed point - the "transitive
closure" of what the cards and the family tree prove). No probabilities and no wild odds are involved.

If an animal is left with no possible pair, its recorded family can't be right (a wrong parent, or a misread card).
"""
from itertools import product

import genetics

STRENGTH = {"G": 2, "O": 1, "B": 0}
ALL_PAIRS = ["GG", "GO", "GB", "OO", "OB", "BB"]


def _pair(a: str, b: str) -> str:
    return "".join(sorted(a + b, key=lambda c: -STRENGTH[c]))


def _allowed_by_card(top: str) -> set:
    if top == "?":
        return set(ALL_PAIRS)
    return {p for p in ALL_PAIRS if p[0] == top}


def closure(animals) -> dict:
    """{"domains": {animal id: [set of possible pairs per gene]}, "conflicts": [(lamb id, gene, mother id, father id)]}"""
    by_id = {a.id: a for a in animals}
    domains = {a.id: [_allowed_by_card(a.genes_top[i]) for i in range(len(genetics.GENES))] for a in animals}
    trios = [(a.id, a.mother_id if a.mother_id in by_id else None, a.father_id if a.father_id in by_id else None)
             for a in animals if (a.mother_id in by_id) or (a.father_id in by_id)]
    conflicts = []
    for g in range(len(genetics.GENES)):
        changed = True
        while changed:
            changed = False
            for child, mother, father in trios:
                cd = domains[child][g]
                md = domains[mother][g] if mother else set(ALL_PAIRS)
                fd = domains[father][g] if father else set(ALL_PAIRS)
                keep_c, keep_m, keep_f = set(), set(), set()
                for m, f in product(md, fd):
                    made = {_pair(x, y) for x in m for y in f} & cd
                    if made:
                        keep_c |= made
                        keep_m.add(m)
                        keep_f.add(f)
                if not keep_c:  # nothing fits: the record is wrong somewhere
                    conflicts.append((child, g, mother, father))
                    continue
                for who, old, new in ((child, cd, keep_c), (mother, md, keep_m), (father, fd, keep_f)):
                    if who and new != old:
                        domains[who][g] = new
                        changed = True
    conflicts = sorted(set(conflicts))
    in_conflict = {x for c in conflicts for x in (c[0], c[2], c[3]) if x}
    return {"domains": domains, "conflicts": conflicts, "in_conflict": in_conflict}
