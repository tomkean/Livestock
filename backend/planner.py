"""Breeding planner: the fastest route (wall-clock time) from the current herd to a god male.

A god male is Good/Good on every gene. Mated to any female, every offspring expresses Good on every gene.

The herd is simulated forward with the game's timings (MECHANICS.md, published figures): gestation, growth, cooldowns
set by the Fertility gene, twins for Good-F mothers, 50/50 sex, one copy of each gene and one lineage marker from each
parent. A greedy policy decides who mates whenever animals are free. Many simulated futures give the expected time,
and comparing first moves across them gives the recommendation for right now.

Alleles are ints: 2 = Good, 1 = Ok, 0 = Bad. A genotype is one (copy, copy) pair per gene.
"""
import random
from dataclasses import dataclass, field
from statistics import median

import genetics

GOOD, OK, BAD = 2, 1, 0
LETTER = {"G": GOOD, "O": OK, "B": BAD}
N_GENES = len(genetics.GENES)
F_GENE = genetics.GENES.index("F")

GESTATION = 10.0  # minutes
GROWTH = 60.0  # minutes from birth to adult; measured on a test server, not published
FEMALE_COOLDOWN = 66.0  # after giving birth, for an Ok-F female; divided by the F multiplier
MALE_COOLDOWN = 10.0  # after mating, for an Ok-F male
TWIN_CHANCE = 0.6  # Good-F mothers only
# F multiplier by expressed band, normal and inbred (inbreeding halves the slider: Good acts as Ok).
F_MULT = {GOOD: (1.6, 1.0), OK: (1.0, 0.825), BAD: (0.65, 0.6)}

HORIZON = 48 * 60.0  # give up on a simulated future after this many minutes
# Surplus animals are sold or butchered: the simulated herd keeps at most this many of each sex (or the starting
# number, if larger), dropping the least useful. Without it the herd grows without limit and the search crawls.
KEEP = {"F": 12, "M": 4}


@dataclass
class Beast:
    id: int  # herd id, or negative for animals born in a simulation
    sex: str
    genes: tuple  # ((a, b), ...) per gene
    markers: tuple  # (m1, m2); unknown markers are unique placeholders
    adult_at: float = 0.0
    free_at: float = 0.0
    name: str = ""
    goods: tuple = ()  # number of Good copies per gene (0, 1 or 2), filled in from genes

    def __post_init__(self):
        self.goods = tuple((a == GOOD) + (b == GOOD) for a, b in self.genes)

    @property
    def inbred(self) -> bool:
        return self.markers[0] == self.markers[1]

    def f_mult(self) -> float:
        return F_MULT[max(self.genes[F_GENE])][1 if self.inbred else 0]

    def is_god(self) -> bool:
        return all(g == 2 for g in self.goods)


def _sample_genes(top: str, bottom: str | None, rng: random.Random) -> tuple:
    """A genotype consistent with the card. An unknown second copy is drawn from the prior in genetics.py."""
    out = []
    for i in range(N_GENES):
        dist = genetics.gene_genotypes(top[i], bottom[i] if bottom else None)
        pair = rng.choices(list(dist), weights=list(dist.values()))[0]
        out.append((LETTER[pair[0]], LETTER[pair[1]]))
    return tuple(out)


def herd_from_animals(animals, now_minutes: float, rng: random.Random) -> list[Beast]:
    """Adult-or-growing members of the herd as Beasts, with times relative to now (0)."""
    herd = []
    for a in animals:
        markers = (a.herd_top if a.herd_top is not None else f"?{a.id}a",
                   a.herd_bottom if a.herd_bottom is not None else f"?{a.id}b")
        genes = _sample_genes(a.genes_top, a.genes_bottom, rng)
        age = getattr(a, "age_minutes", None)
        adult_at = GROWTH - age if age is not None and age < GROWTH else 0.0
        free_at = max(adult_at, getattr(a, "free_in_minutes", 0.0) or 0.0)  # cooldown after her last birth
        beast = Beast(a.id, a.sex, genes, markers, adult_at=adult_at, free_at=free_at, name=a.name or a.code)
        if a.sex == "F" and a.pregnant:
            # Not known when she conceived: assume the birth is imminent and her cooldown follows it.
            beast.free_at = max(adult_at, GESTATION + FEMALE_COOLDOWN / beast.f_mult())
        herd.append(beast)
    return herd


# ---------------------------------------------------------------- policy

def p_god_male(f: Beast, m: Beast) -> float:
    p = 0.5
    for cf, cm in zip(f.goods, m.goods):
        p *= cf * cm / 4
    return p


def scarcity(herd: list[Beast]) -> list[float]:
    """Weight per gene: the fewer Good copies the herd holds, the more a new one is worth."""
    totals = [0] * N_GENES
    for b in herd:
        for i, c in enumerate(b.goods):
            totals[i] += c
    return [1.0 / (1 + t) for t in totals]


def pair_score(f: Beast, m: Beast, partners: list[Beast], weights: list[float]) -> float:
    """How useful one birth from this pair is.

    Three terms, in falling order of size:
    - its chance of being the god male;
    - the chance its child, mated with the best partner available (anyone in the herd, or a sibling), produces one;
    - Good copies the child is expected to carry, weighted by how scarce each gene's Good copies are in the herd.
      This keeps breeding moving when the herd's Good copies are scattered and no pair is near a god male yet:
      it gathers them into fewer animals, generation by generation.
    """
    now = p_god_male(f, m)
    child = [(cf + cm) / 4 for cf, cm in zip(f.goods, m.goods)]  # expected fraction of Good copies per gene
    best = 1.0
    for x in child:
        best *= x * x  # sibling × sibling
    for p in partners:
        v = 1.0
        for x, cp in zip(child, p.goods):
            v *= x * cp / 2
            if v == 0:
                break
        best = max(best, v)
    gather = sum(w * x for w, x in zip(weights, child)) / N_GENES
    return now + 0.25 * best + 0.001 * gather


def choose_matings(herd: list[Beast], t: float, fixed: dict | None = None) -> list[tuple[Beast, Beast]]:
    """Greedy: repeatedly take the best-scoring free female/male pair. `fixed` forces the first choice for some females."""
    females = [b for b in herd if b.sex == "F" and b.adult_at <= t and b.free_at <= t]
    males = [b for b in herd if b.sex == "M" and b.adult_at <= t and b.free_at <= t]
    adults = [b for b in herd if b.adult_at <= t]
    weights = scarcity(herd)
    pairs = []
    if fixed:
        for f in list(females):
            choice = fixed.get(f.id, "greedy")
            if choice == "greedy":
                continue
            females.remove(f)
            m = next((x for x in males if x.id == choice), None)
            if m is not None:
                pairs.append((f, m))
                males.remove(m)
    scored = sorted(((pair_score(f, m, adults, weights), f.id, m.id, f, m) for f in females for m in males),
                    key=lambda s: -s[0])
    used_f, used_m = set(), set()
    for score, _, _, f, m in scored:
        if score <= 0 or f.id in used_f or m.id in used_m:
            continue
        pairs.append((f, m))
        used_f.add(f.id)
        used_m.add(m.id)
    return pairs


# ---------------------------------------------------------------- simulation

@dataclass
class Outcome:
    god_at: float | None  # minutes until a god male is born, or None within the horizon
    births: int = 0
    first: list = field(default_factory=list)  # (female id, male id) chosen at time 0


def _child(f: Beast, m: Beast, rng: random.Random, t: float, next_id: int) -> Beast:
    genes = tuple((rng.choice(fa), rng.choice(ma)) for fa, ma in zip(f.genes, m.genes))
    markers = (rng.choice(f.markers), rng.choice(m.markers))
    return Beast(next_id, rng.choice("FM"), genes, markers, adult_at=t + GROWTH, free_at=t + GROWTH)


def breeding_value(b: Beast, weights: list[float]) -> float:
    """How much an animal is worth keeping: Good copies held, weighted by scarcity, with a bonus for Good/Good."""
    return sum(w * (c + (c == 2)) for w, c in zip(weights, b.goods))


def _cull(herd: list[Beast], keep: dict):
    weights = scarcity(herd)
    for sex, limit in keep.items():
        members = [b for b in herd if b.sex == sex]
        if len(members) <= limit:
            continue
        # Never sell a pregnant female: her lamb is already on the way.
        candidates = sorted((b for b in members if b.free_at != float("inf")), key=lambda b: breeding_value(b, weights))
        for b in candidates[:len(members) - limit]:
            herd.remove(b)


def simulate(herd: list[Beast], rng: random.Random, fixed: dict | None = None) -> Outcome:
    herd = [Beast(b.id, b.sex, b.genes, b.markers, b.adult_at, b.free_at, b.name) for b in herd]
    keep = {sex: max(n, sum(b.sex == sex for b in herd)) for sex, n in KEEP.items()}
    births: list[tuple[float, Beast, Beast]] = []
    t, next_id, born = 0.0, -1, 0
    first = None
    while t <= HORIZON:
        due = [b for b in births if b[0] <= t]
        births = [b for b in births if b[0] > t]
        for when, f, m in due:
            litter = 2 if max(f.genes[F_GENE]) == GOOD and not f.inbred and rng.random() < TWIN_CHANCE else 1
            for _ in range(litter):
                child = _child(f, m, rng, when, next_id)
                next_id -= 1
                born += 1
                if child.sex == "M" and child.is_god():
                    return Outcome(when, born, first or [])
                herd.append(child)
            f.free_at = when + FEMALE_COOLDOWN / f.f_mult()
        if due:
            _cull(herd, keep)
        pairs = choose_matings(herd, t, fixed if first is None else None)
        if first is None:
            first = [(f.id, m.id) for f, m in pairs]
        for f, m in pairs:
            births.append((t + GESTATION, f, m))
            f.free_at = float("inf")  # pregnant until the birth sets her cooldown
            m.free_at = t + MALE_COOLDOWN / m.f_mult()
        upcoming = [b[0] for b in births] + [x for b in herd for x in (b.free_at, b.adult_at) if x > t and x != float("inf")]
        if not upcoming:
            return Outcome(None, born, first or [])
        t = min(upcoming)
    return Outcome(None, born, first or [])


# ---------------------------------------------------------------- plan

def missing_genes(animals) -> list[str]:
    """Genes with no Good copy anywhere in the herd: no plan can produce a god male without new animals.

    The stronger copy is always the one on top, so a gene has a Good copy somewhere exactly when some animal shows
    Good (or an unread '?') on top.
    """
    return [name for i, name in enumerate(genetics.GENES) if not any(a.genes_top[i] in "G?" for a in animals)]


def _summary(times: list, runs: int) -> dict:
    found = sorted(t for t in times if t is not None)
    if not found:
        return {"success": 0.0, "median": None, "p90": None}
    return {
        "success": len(found) / runs,
        "median": median(found),
        "p90": found[min(len(found) - 1, int(0.9 * len(found)))] if len(found) >= 0.9 * runs else None,
    }


def plan(animals, runs: int = 300, seed: int = 1, keep: dict | None = None) -> dict:
    """Recommended matings for now, and how long a god male is expected to take.

    `keep` caps the simulated herd per sex (the pen capacities): surplus animals are assumed sold.
    """
    global KEEP
    if keep:
        KEEP = {"F": int(keep.get("F", KEEP["F"])), "M": int(keep.get("M", KEEP["M"]))}
    rng = random.Random(seed)
    missing = missing_genes(animals)
    if missing:
        return {"possible": False, "missing": missing,
                "reason": "No animal in the herd carries a Good copy of " + ", ".join(missing)
                          + ", so no breeding plan can produce a god male. Bring in an animal showing Good on it."}

    def herd():
        return herd_from_animals(animals, 0, rng)

    def futures(n: int, fixed: dict | None = None) -> list[Outcome]:
        # Common random numbers: run k of every option sees the same luck (hidden copies, litters, sexes,
        # inheritance), so differences between options come from the choice and not from chance.
        out = []
        for k in range(n):
            r = random.Random(seed * 100003 + k)
            out.append(simulate(herd_from_animals(animals, 0, r), r, fixed=fixed))
        return out

    # The greedy policy on its own.
    base = futures(runs)
    result = {"possible": True, "greedy": _summary([o.god_at for o in base], runs)}

    # Compare first moves: for each female free now, try each male (and resting) with greedy play afterwards.
    sample = herd()
    free_f = [b for b in sample if b.sex == "F" and b.adult_at <= 0 and b.free_at <= 0]
    free_m = [b for b in sample if b.sex == "M" and b.adult_at <= 0 and b.free_at <= 0]
    trial_runs = max(40, runs // 4)
    choice = {}
    for f in free_f:
        options = []
        for m_id in [m.id for m in free_m] + [None]:
            outcomes = futures(trial_runs, fixed={f.id: m_id})
            times = [o.god_at if o.god_at is not None else HORIZON * 1.5 for o in outcomes]
            options.append((sum(times) / len(times), m_id))
        options.sort(key=lambda o: o[0])
        choice[f.id] = options[0][1]

    # Males can only take one female at a time: keep each male's best-scoring female, rest the others.
    final = futures(runs, fixed=choice)
    first_counts: dict = {}
    for o in final:
        for pair in o.first:
            first_counts[pair] = first_counts.get(pair, 0) + 1
    names = {b.id: b.name for b in sample}
    matings = [{"female_id": f_id, "male_id": m_id, "female": names.get(f_id), "male": names.get(m_id),
                "p_god_male": p_god_male(next(b for b in sample if b.id == f_id), next(b for b in sample if b.id == m_id))}
               for (f_id, m_id), n in sorted(first_counts.items(), key=lambda kv: -kv[1]) if n >= runs / 2]
    result.update({
        "matings": matings,
        "expected": _summary([o.god_at for o in final], runs),
        "births": median(o.births for o in final),
        "runs": runs,
        "assumptions": [
            f"Growth to adult {GROWTH:.0f} min (test server)",
            "Second rows taken from the cards where known; otherwise drawn from the even prior",
            "A female's cooldown runs from her last recorded lamb; unrecorded births aren't known",
        ],
    })
    return result


# ---------------------------------------------------------------- barn trips

# How many animals one trip carries, by vehicle and species (MECHANICS.md, transport). Calves count as sheep.
TRUCK = {
    "lead": {"sheep": 1, "calf": 1, "cow": 1},  # on foot, e.g. a base beside the barn; one animal at a time assumed
    "single": {"sheep": 1, "calf": 1, "cow": 0},
    "double": {"sheep": 2, "calf": 2, "cow": 1},
}
RAMS_KEPT = 2


def _visible_goods(a) -> tuple:
    """Good copies the cards show: both rows where known, otherwise the top row (green = at least one)."""
    out = []
    for i in range(N_GENES):
        top = a.genes_top[i] == "G"
        bottom = bool(a.genes_bottom) and a.genes_bottom[i] == "G"
        out.append(int(top) + int(bottom))
    return tuple(out)


def trip_plan(animals, species: str, vehicle: str, keep: dict, planned: set = frozenset()) -> dict:
    """What to sell and what to buy on the next trip to the barn.

    Sell: grown animals the breeding project doesn't need - rams beyond the best RAMS_KEPT, then the weakest ewes
    beyond the pen capacity - never the last animal showing green on a gene, nor one the plan wants to mate now
    (`planned`). Buy: a ram if there's none, otherwise
    ewes until the pen is full and every gene shows green somewhere. Both limited by what the truck carries.
    """
    grown = [a for a in animals if not getattr(a, "is_lamb", False)]
    herd = [SimpleBeast(a, _visible_goods(a)) for a in animals]
    weights = [1.0 / (1 + sum(b.goods[i] for b in herd)) for i in range(N_GENES)]

    def value(b):
        return sum(w * (c + (c == 2)) for w, c in zip(weights, b.goods))

    def last_carrier(b, pool):
        return any(b.goods[i] and not any(o is not b and o.goods[i] for o in pool) for i in range(N_GENES))

    adult_cap = TRUCK[vehicle]["cow" if species == "cow" else "sheep"]
    lamb_cap = TRUCK[vehicle]["calf" if species == "cow" else "sheep"]

    pool = list(herd)
    sell = []
    grown_ids = {a.id for a in grown}
    for sex, limit in (("M", RAMS_KEPT), ("F", int(keep.get("F", KEEP["F"])))):
        members = sorted((b for b in pool if b.sex == sex), key=value, reverse=True)
        for b in reversed(members[limit:]):
            if len(sell) >= adult_cap:
                break
            if b.id in grown_ids and b.id not in planned and not last_carrier(b, pool):
                sell.append(b)
                pool.remove(b)

    missing = [genetics.GENES[i] for i in range(N_GENES) if not any(b.goods[i] for b in pool)]
    buy = []
    ewes = sum(b.sex == "F" for b in pool)
    rams = sum(b.sex == "M" for b in pool)
    ewe_target = int(keep.get("F", KEEP["F"]))
    for _ in range(lamb_cap):
        if rams == 0:
            buy.append("M"); rams += 1
        elif ewes < ewe_target or missing:
            buy.append("F"); ewes += 1
    return {
        "vehicle": vehicle,
        "sell": [{"id": b.id, "name": b.name, "sex": b.sex} for b in sell],
        "buy": buy,
        "missing": missing,
        "capacity": {"adults": adult_cap, "young": lamb_cap},
        "done_buying": not buy,
    }


class SimpleBeast:
    """An animal as the trip planner sees it: what its cards show, nothing sampled."""
    id: int
    sex: str
    name: str
    goods: tuple

    def __init__(self, animal, goods):
        self.id, self.sex, self.name, self.goods = animal.id, animal.sex, animal.name or animal.code, goods
