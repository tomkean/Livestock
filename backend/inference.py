"""Infers the hidden second copy of every gene from what a live-server player can see.

On a normal server the card shows only the expressed (stronger) copy. The hidden copy is inferred from:
- the animal's own top row: the stronger copy shows, so green = at least one Good, grey = no Good, red = Bad/Bad;
- the wild odds for animals with no recorded parents (each copy Good 20%, Ok 50%, Bad 30%);
- its recorded parents (each passes one copy at random) and its recorded lambs (whose top rows constrain it).

Genes are inherited independently, so each gene is solved on its own. The pedigree can loop (inbreeding), so the
posterior is estimated by Gibbs sampling: repeatedly re-drawing one animal's copies given its parents, its own card
and its lambs. Each animal holds an ordered pair (copy from mother, copy from father); animals without recorded
parents hold two copies drawn from the wild odds.

Second rows captured on a test server are never used here; they are what the inference is checked against.
"""
import random

import genetics

ALLELES = (2, 1, 0)  # Good, Ok, Bad
LETTER_TO = {"G": 2, "O": 1, "B": 0}
TO_LETTER = {2: "G", 1: "O", 0: "B"}
WILD = {2: 0.2, 1: 0.5, 0: 0.3}
# Annealing: early sweeps allow a little "impossible" inheritance and card mismatch so the sampler can't get stuck
# (a lamb's guessed copy ruling out its mother's true copy and vice versa). Both shrink to ~0 before sampling starts.
SLACK_START, SLACK_END = 0.2, 1e-6


class Pedigree:
    def __init__(self, animals):
        self.animals = list(animals)
        self.index = {a.id: i for i, a in enumerate(self.animals)}
        self.mother = [self.index.get(a.mother_id) for a in self.animals]
        self.father = [self.index.get(a.father_id) for a in self.animals]
        self.children = [[] for _ in self.animals]
        for i in range(len(self.animals)):
            for p in (self.mother[i], self.father[i]):
                if p is not None:
                    self.children[p].append(i)


def _observed(top: str):
    return LETTER_TO.get(top)  # None when unread ('?')


def _parent_copy_prob(state, allele, slack: float = 0.0) -> float:
    """Chance a parent in `state` (a, b) passes `allele`, with a little slack while annealing."""
    a, b = state
    p = 0.5 * (a == allele) + 0.5 * (b == allele)
    return (1 - slack) * p + slack / 3


def _gene_samples(ped: Pedigree, gene: int, rng: random.Random, sweeps: int, burn: int, thin: int):
    n = len(ped.animals)
    obs = [_observed(a.genes_top[gene]) for a in ped.animals]

    def fits(i, state):
        o = obs[i]
        return o is None or max(state) == o

    # Start: each animal's top copy as shown and a hidden copy no stronger, top-down so parents come first.
    state = [None] * n
    order = sorted(range(n), key=lambda i: _depth(ped, i))
    for i in order:
        o = obs[i] if obs[i] is not None else rng.choice(ALLELES)
        hidden = rng.choice([x for x in ALLELES if x <= o])
        state[i] = (o, hidden) if rng.random() < 0.5 else (hidden, o)

    candidates = [(a, b) for a in ALLELES for b in ALLELES]
    out = []
    for sweep in range(sweeps):
        # Slack falls geometrically over the burn-in, then stays at its floor while samples are kept.
        slack = SLACK_END if sweep >= burn else SLACK_START * (SLACK_END / SLACK_START) ** (sweep / max(1, burn - 1))
        for i in range(n):
            m, f = ped.mother[i], ped.father[i]
            weights = []
            for cand in candidates:
                a, b = cand  # a from mother, b from father
                w = (_parent_copy_prob(state[m], a, slack) if m is not None else WILD[a]) * \
                    (_parent_copy_prob(state[f], b, slack) if f is not None else WILD[b])
                if not fits(i, cand):
                    w *= slack
                for c in ped.children[i]:
                    ca, cb = state[c]
                    copy = ca if ped.mother[c] == i else cb  # the copy this child got from i
                    w *= _parent_copy_prob(cand, copy, slack)
                weights.append(w)
            total = sum(weights)
            if total > 0:
                state[i] = rng.choices(candidates, weights=weights)[0]
        if sweep >= burn and (sweep - burn) % thin == 0:
            out.append(list(state))
    return out


def _depth(ped: Pedigree, i: int, seen=None) -> int:
    seen = seen or set()
    if i in seen:
        return 0
    seen.add(i)
    parents = [p for p in (ped.mother[i], ped.father[i]) if p is not None]
    return 1 + max((_depth(ped, p, seen) for p in parents), default=0)


def infer(animals, sweeps: int = 1500, burn: int = 300, thin: int = 5, seed: int = 1) -> dict:
    """Posterior over each animal's genotype, gene by gene, from top rows and pedigree only.

    Returns {"posterior": {animal_id: [{"GG": p, "GO": p, ...} per gene]}, "samples": [joint samples per gene]}.
    A joint sample is one consistent guess of everyone's copies: {animal_id: ((a, b) per gene)}.
    """
    rng = random.Random(seed)
    ped = Pedigree(animals)
    per_gene = [_gene_samples(ped, g, rng, sweeps, burn, thin) for g in range(len(genetics.GENES))]
    n_samples = len(per_gene[0])
    posterior = {}
    for i, a in enumerate(ped.animals):
        genes = []
        for g in range(len(genetics.GENES)):
            counts = {}
            for s in per_gene[g]:
                x, y = s[i]
                key = TO_LETTER[max(x, y)] + TO_LETTER[min(x, y)]
                counts[key] = counts.get(key, 0) + 1
            genes.append({k: v / n_samples for k, v in counts.items()})
        posterior[a.id] = genes
    samples = [{a.id: tuple(per_gene[g][k][i] for g in range(len(genetics.GENES))) for i, a in enumerate(ped.animals)}
               for k in range(n_samples)]
    return {"posterior": posterior, "samples": samples}


def validate(animals, **kw) -> dict:
    """Check the inference against second rows captured on a test server (which it never sees)."""
    known = [a for a in animals if a.genes_bottom and "?" not in a.genes_bottom]
    result = infer(animals, **kw)
    right = total = 0
    log_loss = 0.0
    import math
    rows = []
    for a in known:
        for g, name in enumerate(genetics.GENES):
            truth = "".join(sorted(a.genes_top[g] + a.genes_bottom[g], key=lambda c: -LETTER_TO[c]))
            dist = result["posterior"][a.id][g]
            guess = max(dist, key=dist.get)
            right += guess == truth
            total += 1
            log_loss -= math.log(max(dist.get(truth, 0.0), 1e-6))
            rows.append((a.name or a.code, name, truth, guess, round(dist.get(truth, 0.0), 2)))
    return {"genes_checked": total, "best_guess_right": right / total if total else None,
            "avg_prob_on_truth": math.exp(-log_loss / total) if total else None, "rows": rows}
