"""Livestock genetics rules. MECHANICS.md records which of these are confirmed and which are guesses."""

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


def gene_genotypes(top: str, bottom: str | None) -> dict[str, float]:
    """Possible genotypes of one gene, with probabilities.

    The card shows the stronger copy on top. When the second copy is unknown it can be anything no stronger
    than the top one, and each possibility is taken as equally likely. That is a placeholder prior: inferring
    the hidden copy from relatives will replace it.
    """
    tops = [top] if top in STRENGTH else list(STRENGTH)
    out: dict[str, float] = {}
    for t in tops:
        if bottom in STRENGTH:
            bottoms = [bottom]
        else:
            bottoms = [a for a in STRENGTH if STRENGTH[a] <= STRENGTH[t]]
        for b in bottoms:
            g = _pair(t, b)
            out[g] = out.get(g, 0.0) + 1.0 / (len(tops) * len(bottoms))
    return out


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


def mating_odds(mother, father) -> dict:
    """Odds for one offspring of a mating, under the rules in MECHANICS.md.

    Per gene: chance of each genotype and of each expressed colour. Overall: chance the offspring is inbred
    (its two lineage markers match), chance it expresses Good on every gene, and chance it is a god male
    (Good/Good on every gene) assuming offspring sex is 50/50.
    """
    genes = []
    p_all_good = 1.0
    p_god = 1.0
    for i, name in enumerate(GENES):
        mg = _gametes(gene_genotypes(mother.genes_top[i], (mother.genes_bottom or "")[i:i + 1] or None))
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
