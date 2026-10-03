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


def herds(animal) -> set[int]:
    return {h for h in (animal.herd_top, animal.herd_bottom) if h is not None}


def shares_herd(a, b) -> bool:
    """Incest per the herd-number rule: the parents have a herd number in common."""
    return bool(herds(a) & herds(b))


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
