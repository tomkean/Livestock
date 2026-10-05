"""Breeding planner: the fastest route (wall-clock time) from the current herd to a god male.

A god male is Good/Good on every gene. Mated to any female, every offspring expresses Good on every gene.

The herd is simulated forward with the game's timings (MECHANICS.md, published figures): gestation, growth, cooldowns
set by the Fertility gene, twins for Good-F mothers, 50/50 sex, one copy of each gene and one lineage marker from each
parent. A greedy policy decides who mates whenever animals are free. Many simulated futures give the expected time,
and comparing first moves across them gives the recommendation for right now.

Alleles are ints: 2 = Good, 1 = Ok, 0 = Bad. A genotype is one (copy, copy) pair per gene.
"""
import random
from dataclasses import dataclass, field, replace
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
    # Good copies per gene as the player believes them - what every decision is based on. With both rows visible
    # (test server) that is the truth, filled in from genes. In live mode it is the inferred expectation, and `genes`
    # (one consistent guess of the hidden copies) only decides inheritance and whether a god male really exists.
    goods: tuple = ()
    informed: bool = True

    def __post_init__(self):
        if not self.goods:
            self.goods = tuple((a == GOOD) + (b == GOOD) for a, b in self.genes)

    @property
    def inbred(self) -> bool:
        return self.markers[0] == self.markers[1]

    def f_mult(self) -> float:
        return F_MULT[max(self.genes[F_GENE])][1 if self.inbred else 0]

    def is_god(self) -> bool:
        return all(a == GOOD and b == GOOD for a, b in self.genes)  # the truth, not the belief


def _sample_genes(top: str, bottom: str | None, rng: random.Random) -> tuple:
    """A genotype consistent with the card. An unknown second copy is drawn from the prior in genetics.py."""
    out = []
    for i in range(N_GENES):
        dist = genetics.gene_genotypes(top[i], bottom[i] if bottom else None)
        pair = rng.choices(list(dist), weights=list(dist.values()))[0]
        out.append((LETTER[pair[0]], LETTER[pair[1]]))
    return tuple(out)


def herd_from_animals(animals, now_minutes: float, rng: random.Random, target: str = "",
                      sample: dict | None = None, posterior: dict | None = None) -> list[Beast]:
    """Adult-or-growing members of the herd as Beasts, with times relative to now (0).

    Genes not in `target` are treated as already Good/Good, so every part of the search ignores them.
    Live mode passes `sample` (one consistent guess of everyone's hidden copies, from inference.py) and `posterior`
    (what can actually be believed about each animal); otherwise the cards' rows are taken as the truth.
    """
    ignore = [g not in target for g in genetics.GENES] if target else [False] * N_GENES
    herd = []
    for a in animals:
        markers = (a.herd_top if a.herd_top is not None else f"?{a.id}a",
                   a.herd_bottom if a.herd_bottom is not None else f"?{a.id}b")
        if sample is not None and a.id in sample:
            sampled = sample[a.id]
        else:
            sampled = _sample_genes(a.genes_top, a.genes_bottom, rng)
        genes = tuple((GOOD, GOOD) if skip else pair for skip, pair in zip(ignore, sampled))
        belief = ()
        if posterior is not None and a.id in posterior:
            belief = tuple(2.0 if skip else sum(p * key.count("G") for key, p in dist.items())
                           for skip, dist in zip(ignore, posterior[a.id]))
        age = getattr(a, "age_minutes", None)
        adult_at = GROWTH - age if age is not None and age < GROWTH else 0.0
        free_at = max(adult_at, getattr(a, "free_in_minutes", 0.0) or 0.0)  # cooldown after her last birth
        beast = Beast(a.id, a.sex, genes, markers, adult_at=adult_at, free_at=free_at, name=a.name or a.code,
                      goods=belief, informed=not belief)
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
    child = Beast(next_id, rng.choice("FM"), genes, markers, adult_at=t + GROWTH, free_at=t + GROWTH)
    if not (f.informed and m.informed):
        # A live-server player sees only the lamb's top row: green means at least one Good copy. Its expected Good
        # copies follow from what is believed about each parent (q = chance that parent passes a Good copy).
        belief = []
        for (a, b), cf, cm in zip(genes, f.goods, m.goods):
            if max(a, b) != GOOD:
                belief.append(0.0)
                continue
            qf, qm = cf / 2, cm / 2
            seen = 1 - (1 - qf) * (1 - qm)
            belief.append((qf + qm) / seen if seen > 0 else 1.0)
        child.goods, child.informed = tuple(belief), False
    return child


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
    herd = [replace(b) for b in herd]
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

def missing_genes(animals, target: str = "DLYFH") -> list[str]:
    """Genes with no Good copy anywhere in the herd: no plan can produce a god male without new animals.

    The stronger copy is always the one on top, so a gene has a Good copy somewhere exactly when some animal shows
    Good (or an unread '?') on top.
    """
    return [name for i, name in enumerate(genetics.GENES)
            if name in target and not any(a.genes_top[i] in "G?" for a in animals)]


def _summary(times: list, runs: int) -> dict:
    found = sorted(t for t in times if t is not None)
    if not found:
        return {"success": 0.0, "median": None, "p90": None}
    return {
        "success": len(found) / runs,
        "median": median(found),
        "p90": found[min(len(found) - 1, int(0.9 * len(found)))] if len(found) >= 0.9 * runs else None,
    }


def plan(animals, runs: int = 300, seed: int = 1, keep: dict | None = None, target: str = "DLYFH",
         inferred: dict | None = None) -> dict:
    """Recommended matings for now, and how long a god male is expected to take.

    `keep` caps the simulated herd per sex (the pen capacities): surplus animals are assumed sold.
    """
    global KEEP
    if keep:
        KEEP = {"F": int(keep.get("F", KEEP["F"])), "M": int(keep.get("M", KEEP["M"]))}
    rng = random.Random(seed)
    target = "".join(g for g in genetics.GENES if g in (target or "")) or "".join(genetics.GENES)
    missing = missing_genes(animals, target)
    if missing:
        return {"possible": False, "missing": missing,
                "reason": "No animal in the herd carries a Good copy of " + ", ".join(missing)
                          + ", so no breeding plan can produce a god male. Bring in an animal showing Good on it."}

    samples = (inferred or {}).get("samples") or []
    posterior = (inferred or {}).get("posterior")

    def herd(k: int = 0, r: random.Random = rng):
        sample = samples[k % len(samples)] if samples else None
        return herd_from_animals(animals, 0, r, target, sample=sample, posterior=posterior)

    def futures(n: int, fixed: dict | None = None) -> list[Outcome]:
        # Common random numbers: run k of every option sees the same luck (hidden copies, litters, sexes,
        # inheritance), so differences between options come from the choice and not from chance.
        out = []
        for k in range(n):
            r = random.Random(seed * 100003 + k)
            out.append(simulate(herd(k, r), r, fixed=fixed))
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
        "target": target,
        "matings": matings,
        "expected": _summary([o.god_at for o in final], runs),
        "births": median(o.births for o in final),
        "runs": runs,
        "mode": "live (top rows + inference)" if posterior is not None else "both rows visible",
        "assumptions": [
            f"Growth to adult {GROWTH:.0f} min (test server)",
            ("Hidden copies inferred from top rows and family (live mode); decisions use only what a player can see"
             if posterior is not None else "Second rows taken from the cards (test-server mode)"),
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


def _visible_goods(a, target: str = "DLYFH", posterior: dict | None = None) -> tuple:
    """Good copies the cards show: both rows where known, otherwise the top row (green = at least one).
    Genes outside the target count as fully Good, so they never decide anything."""
    out = []
    for i in range(N_GENES):
        if genetics.GENES[i] not in target:
            out.append(2)
            continue
        if posterior is not None and a.id in posterior:
            out.append(sum(p * key.count("G") for key, p in posterior[a.id][i].items()))
            continue
        top = a.genes_top[i] == "G"
        bottom = bool(a.genes_bottom) and a.genes_bottom[i] == "G"
        out.append(int(top) + int(bottom))
    return tuple(out)


def trip_plan(animals, species: str, vehicle: str, keep: dict, planned: set = frozenset(), target: str = "DLYFH",
              posterior: dict | None = None) -> dict:
    """What to sell and what to buy on the next trip to the barn.

    Sell: grown animals the breeding project doesn't need - rams beyond the best RAMS_KEPT, then the weakest ewes
    beyond the pen capacity - never the last animal showing green on a gene, nor a pregnant female, nor one the plan wants to mate now
    (`planned`). Buy: a ram if there's none, otherwise
    ewes until the pen is full and every gene shows green somewhere. Both limited by what the truck carries.
    """
    grown = [a for a in animals if not getattr(a, "is_lamb", False)]
    herd = [SimpleBeast(a, _visible_goods(a, target, posterior)) for a in animals]
    weights = [1.0 / (1 + sum(b.goods[i] for b in herd)) for i in range(N_GENES)]

    def value(b):
        return sum(w * (c + (c == 2)) for w, c in zip(weights, b.goods))

    def last_carrier(b, pool):
        return any(b.goods[i] > 0.5 and not any(o is not b and o.goods[i] > 0.5 for o in pool) for i in range(N_GENES))

    adult_cap = TRUCK[vehicle]["cow" if species == "cow" else "sheep"]
    lamb_cap = TRUCK[vehicle]["calf" if species == "cow" else "sheep"]

    pool = list(herd)
    sell = []
    grown_ids = {a.id for a in grown}
    for sex, limit in (("M", RAMS_KEPT), ("F", int(keep.get("F", KEEP["F"])))):
        members = sorted((b for b in pool if b.sex == sex), key=value)  # weakest first
        surplus = len(members) - limit
        # Sell the weakest that may be sold; if one can't (pregnant, still a lamb, needed by the plan, last carrier
        # of a green), move on to the next weakest rather than giving up.
        for b in members:
            if surplus <= 0 or len(sell) >= adult_cap:
                break
            if b.id in grown_ids and b.id not in planned and not b.pregnant and not last_carrier(b, pool):
                sell.append(b)
                pool.remove(b)
                surplus -= 1

    missing = [genetics.GENES[i] for i in range(N_GENES) if not any(b.goods[i] > 0.5 for b in pool)]
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
        self.pregnant = bool(getattr(animal, "pregnant", False))  # never sold: her lamb is on the way
