"""Livestock genetics rules. MECHANICS.md records which of these are confirmed and which are guesses."""
from datetime import timezone

GENES = ("D", "L", "Y", "F", "H")  # dung, lifespan, yield, fertility, hardiness
ALLELES = "GOB?"  # good, ok, bad, unknown
SPECIES = ("cow", "sheep")


def normalise_row(row: str) -> str:
    """Validate a gene row such as 'GOG?B'. Raises ValueError if malformed."""
    row = (row or "").strip().upper()
    if len(row) != len(GENES) or any(c not in ALLELES for c in row):
        raise ValueError(f"gene row must be {len(GENES)} of {ALLELES}, got {row!r}")
    return row


STRENGTH = {"B": 0, "O": 1, "G": 2}


def _pair(a: str, b: str) -> str:
    """A genotype written strongest copy first, e.g. 'GB': the first letter is the one expressed."""
    return a + b if STRENGTH[a] >= STRENGTH[b] else b + a


# Wild and bought animals roll each copy independently (published): Good 20%, Ok 50%, Bad 30%.
WILD_COPY = {"G": 0.2, "O": 0.5, "B": 0.3}


def _wild_pair(a: str, b: str) -> float:
    """Chance a wild animal has this unordered pair of copies."""
    p = WILD_COPY[a] * WILD_COPY[b]
    return p if a == b else 2 * p


def gene_genotypes(top: str, bottom: str | None) -> dict[str, float]:
    """Possible genotypes of one gene, with probabilities.

    The card shows the stronger copy on top. When the second copy is unknown, it is any copy no stronger than the
    top one, weighted by how often wild animals carry each pair. E.g. a green gene with an unknown second copy is
    Good/Good 11%, Good/Ok 56%, Good/Bad 33%. Bred animals' hidden copies would be better inferred from their
    parents; this prior is what is known without that.
    """
    tops = [top] if top in STRENGTH else list(STRENGTH)
    out: dict[str, float] = {}
    for t in tops:
        bottoms = [bottom] if bottom in STRENGTH else [a for a in STRENGTH if STRENGTH[a] <= STRENGTH[t]]
        for b in bottoms:
            g = _pair(t, b)
            out[g] = out.get(g, 0.0) + _wild_pair(t, b)
    total = sum(out.values())
    return {g: p / total for g, p in out.items()}


F_MULT = {"G": 1.6, "O": 1.0, "B": 0.65}  # Fertility multiplier on cooldowns, by expressed F (published)
F_MULT_INBRED = {"G": 1.0, "O": 0.825, "B": 0.6}  # inbreeding halves the slider: Good acts as Ok
FEMALE_COOLDOWN_MIN = 66.0  # after a birth, for Ok F
MALE_COOLDOWN_MIN = 10.0  # after mating, for Ok F


def fertility_multiplier(animal) -> float:
    f = animal.genes_top[GENES.index("F")]
    inbred = animal.herd_top is not None and animal.herd_top == animal.herd_bottom
    return (F_MULT_INBRED if inbred else F_MULT).get(f, 1.0)


def _gametes(genotypes: dict[str, float]) -> dict[str, float]:
    """Each parent passes one of its two copies, 50/50."""
    out: dict[str, float] = {}
    for g, p in genotypes.items():
        for allele in g:
            out[allele] = out.get(allele, 0.0) + p / 2
    return out


def _markers(animal, tag: str) -> list:
    # An unknown second marker is represented by a value unique to this animal, so it never matches.
    return [animal.herd_top if animal.herd_top is not None else f"{tag}?top",
            animal.herd_bottom if animal.herd_bottom is not None else f"{tag}?bottom"]


def mating_odds(mother, father, dists: dict | None = None) -> dict:
    """Odds for one offspring of a mating, under the rules in MECHANICS.md.

    Per gene: chance of each genotype and of each expressed colour. Overall: chance the offspring is inbred
    (its two lineage markers match), chance it expresses Good on every gene, and chance it is a god male
    (Good/Good on every gene) assuming offspring sex is 50/50.
    """
    genes = []
    p_all_good = 1.0
    p_god = 1.0
    for i, name in enumerate(GENES):
        # Live mode: what inference believes about each parent's copies; otherwise read from the cards.
        if dists is not None and mother.id in dists:
            mg = _gametes(dists[mother.id][i])
        else:
            mg = _gametes(gene_genotypes(mother.genes_top[i], (mother.genes_bottom or "")[i:i + 1] or None))
        if dists is not None and father.id in dists:
            fg = _gametes(dists[father.id][i])
        else:
            fg = _gametes(gene_genotypes(father.genes_top[i], (father.genes_bottom or "")[i:i + 1] or None))
        genotypes: dict[str, float] = {}
        for a, pa in mg.items():
            for b, pb in fg.items():
                g = _pair(a, b)
                genotypes[g] = genotypes.get(g, 0.0) + pa * pb
        expressed = {a: sum(p for g, p in genotypes.items() if g[0] == a) for a in "GOB"}
        genes.append({"gene": name, "genotypes": genotypes, "expressed": expressed})
        p_all_good *= expressed["G"]
        p_god *= genotypes.get("GG", 0.0)

    m_markers, f_markers = _markers(mother, "m"), _markers(father, "f")
    p_inbred = sum(0.25 for a in m_markers for b in f_markers if a == b)
    markers_known = None not in (mother.herd_top, mother.herd_bottom, father.herd_top, father.herd_bottom)
    rows_known = bool(mother.genes_bottom and father.genes_bottom
                      and "?" not in mother.genes_top + mother.genes_bottom + father.genes_top + father.genes_bottom)
    return {
        "genes": genes,
        "p_inbred": p_inbred,
        "p_all_good": p_all_good,
        "p_god_male": p_god * 0.5,
        "markers_known": markers_known,
        "rows_known": rows_known,
    }


def match_score(animal, observed) -> int | None:
    """How well a stored animal matches a freshly captured card.

    Genes and herd numbers never change, so any conflict between two known values rules the animal out
    (returns None). Otherwise the score is the number of known values that agree.
    """
    pairs = list(zip(animal.genes_top, observed.genes_top))
    if animal.genes_bottom and observed.genes_bottom:
        pairs += zip(animal.genes_bottom, observed.genes_bottom)
    pairs += [(animal.herd_top, observed.herd_top), (animal.herd_bottom, observed.herd_bottom)]

    score = 0
    for stored, seen in pairs:
        if stored in (None, "?") or seen in (None, "?"):
            continue
        if stored != seen:
            return None
        score += 1
    return score


MARKER_VALUES = 16  # markers seen are 0-15; an unknown parent marker matches a given value 1 time in 16


def _marker_chance(parent_markers: list, value) -> float:
    """Chance a parent passes this marker value: each of its two markers is passed half the time."""
    p = 0.0
    for m in parent_markers:
        if m is None:
            p += 0.5 / MARKER_VALUES
        elif m == value:
            p += 0.5
    return p


def parentage_likelihood(child, mother, father, dists: dict | None = None) -> float:
    """How likely this mother and father are to produce exactly what the child's card shows (0 = impossible).

    Genes: the chance of the child's genotype when both rows are known, or of its top row when only that is.
    Markers: one comes from each parent, in either order.
    """
    odds = mating_odds(mother, father, dists)
    p = 1.0
    for i, g in enumerate(odds["genes"]):
        top = child.genes_top[i]
        bottom = (child.genes_bottom or "")[i:i + 1]
        if top == "?":
            continue
        if bottom and bottom != "?":
            p *= g["genotypes"].get(_pair(top, bottom), 0.0)
        else:
            p *= g["expressed"].get(top, 0.0)
        if p == 0:
            return 0.0
    m_markers = [mother.herd_top, mother.herd_bottom]
    f_markers = [father.herd_top, father.herd_bottom]
    x, y = child.herd_top, child.herd_bottom
    if x is not None and y is not None:
        p *= (_marker_chance(m_markers, x) * _marker_chance(f_markers, y)
              + (_marker_chance(m_markers, y) * _marker_chance(f_markers, x) if x != y else 0.0))
    elif x is not None or y is not None:
        v = x if x is not None else y
        p *= 1 - (1 - _marker_chance(m_markers, v)) * (1 - _marker_chance(f_markers, v))
    return p


CONCEPTION_LEAD_MIN = 60 + 10  # a parent must have grown up (60 min) before the 10-minute pregnancy began


def _could_parent(parent, child) -> bool:
    """False only when both birth times are known and the parent was too young to be a parent."""
    p, c = getattr(parent, "born_at", None), getattr(child, "born_at", None)
    if p is None or c is None:
        return True
    p = p if p.tzinfo else p.replace(tzinfo=timezone.utc)
    c = c if c.tzinfo else c.replace(tzinfo=timezone.utc)
    return (c - p).total_seconds() / 60 >= CONCEPTION_LEAD_MIN


ELSEWHERE = 0.05  # weight for each place rule a pair breaks (see likely_parents)


def likely_parents(child, animals, mated_pairs: set = frozenset(), limit: int = 5, dists: dict | None = None,
                   places=None) -> list[dict]:
    """Mother × father pairs that could have produced the child, most likely first, with relative chances.

    A pair with a recorded mating is weighted 10× (it's where lambs usually come from). `places(mother, father)` says
    whether the pair were together when the lamb was conceived and whether the mother was in the lamb's building at
    its birth (a ewe moved while pregnant conceived in her old harem, by its ram). Each rule broken costs a factor of
    20, not a veto: the building records can be wrong. The chances are relative to the other candidates.
    """
    child_id = getattr(child, "id", None)
    pool = [a for a in animals if a.species == child.species and getattr(a, "id", None) != child_id
            and _could_parent(a, child)]
    scored = []
    # An unsexed animal (a lamb that grew up before anyone saw horns) can be either parent; being found as one
    # reveals its sex.
    for m in (a for a in pool if a.sex in ("F", "?")):
        for f in (a for a in pool if a.sex in ("M", "?")):
            if m is f:
                continue
            p = parentage_likelihood(child, m, f, dists)
            if p > 0:
                if (m.id, f.id) in mated_pairs:
                    p *= 10
                together = None
                if places is not None:
                    together, mother_there = places(m, f)
                    p *= (1 if together else ELSEWHERE) * (1 if mother_there else ELSEWHERE)
                scored.append((p, m, f, together))
    total = sum(s[0] for s in scored)
    scored.sort(key=lambda s: -s[0])
    return [{"mother_id": m.id, "father_id": f.id, "chance": p / total, "mated": (m.id, f.id) in mated_pairs,
             "reveals": [x.id for x in (m, f) if x.sex == "?"], "together": bool(together)}
            for p, m, f, together in scored[:limit]]
