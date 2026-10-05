"""Pools mode: harems where each ram mates his ewes freely, plus a holding room ("Death Row").

The player doesn't arrange matings. They keep the best rams heading the harems, put each ewe with the ram she
complements best, and give every lamb a verdict - promote it into a harem, keep it in holding, cull it at birth, or
sell it once grown. Simulated on the test herd this reached a god male in ~8 h against ~9.4 h for hand-picked matings.

Everything here works on beliefs: expected Good copies per gene from inference (live mode) or from the captured rows
(test-server mode). Genes outside the target count as already Good/Good, so they never decide anything.
"""
from types import SimpleNamespace

import genetics
import planner

N = len(genetics.GENES)


def beliefs(animals, target: str, posterior: dict | None) -> dict:
    """Expected Good copies per gene for each animal."""
    out = {}
    for a in animals:
        goods = []
        for i, g in enumerate(genetics.GENES):
            if g not in target:
                goods.append(2.0)
            elif posterior is not None and a.id in posterior:
                goods.append(sum(p * key.count("G") for key, p in posterior[a.id][i].items()))
            else:
                bottom = (a.genes_bottom or "")[i:i + 1]
                goods.append((a.genes_top[i] == "G") + (bottom == "G") if bottom else (1.11 if a.genes_top[i] == "G" else 0.0))
        out[a.id] = tuple(goods)
    return out


def _beast(a, goods):
    return SimpleNamespace(id=a.id, goods=goods)


def _weights(goods_list):
    """Scarcity per gene: the fewer Good copies the herd holds, the more each one is worth."""
    return [1.0 / (1 + sum(g[i] for g in goods_list)) for i in range(N)]


def _value(goods, weights) -> float:
    # Good/Good counts extra: it is passed on every time.
    return sum(w * (c + max(0.0, c - 1)) for w, c in zip(weights, goods))


def arrange(animals, target: str, posterior: dict | None, harems: list[str], holding: str, harem_ewes: int = 8) -> dict:
    """Suggested pen for every animal, plus a verdict and a reason for each one in holding."""
    belief = beliefs(animals, target, posterior)
    weights = _weights(list(belief.values()))
    value = {a.id: _value(belief[a.id], weights) for a in animals}

    grown = [a for a in animals if not getattr(a, "is_lamb", False)]
    rams = sorted((a for a in grown if a.sex == "M"), key=lambda a: -value[a.id])
    heads = rams[:len(harems)]
    pen = {a.id: holding for a in animals}
    members = {h: [] for h in harems}
    head_of = {}
    for name, ram in zip(harems, heads):
        pen[ram.id] = name
        head_of[name] = ram

    def fit(ewe, ram):
        return planner.pair_score(_beast(ewe, belief[ewe.id]), _beast(ram, belief[ram.id]),
                                  [_beast(x, belief[x.id]) for x in animals], weights)

    ewes = sorted((a for a in grown if a.sex == "F"), key=lambda a: -value[a.id])
    for ewe in ewes:
        options = sorted(head_of, key=lambda h: -fit(ewe, head_of[h]))
        for h in options:
            if len(members[h]) < harem_ewes:
                members[h].append(ewe)
                pen[ewe.id] = h
                break

    # Verdicts for everything in holding.
    weakest_ewe = {h: min((value[e.id] for e in members[h]), default=None) for h in members}
    weakest_ram = min((value[r.id] for r in heads), default=None)
    kept_values = [value[a.id] for a in animals if pen[a.id] != holding]
    floor = min(kept_values) if kept_values else 0.0

    def last_carrier(a):
        return any(belief[a.id][i] > 0.5 and not any(o.id != a.id and belief[o.id][i] > 0.5 for o in animals)
                   for i in range(N))

    verdicts = {}
    for a in animals:
        if pen[a.id] != holding:
            continue
        v = value[a.id]
        as_ram = weakest_ram is None or v > weakest_ram
        best_h = max(head_of, key=lambda h: fit(a, head_of[h])) if head_of else None
        as_ewe = best_h is not None and (len(members[best_h]) < harem_ewes or
                                         (weakest_ewe[best_h] is not None and v > weakest_ewe[best_h]))
        lamb = getattr(a, "is_lamb", False)
        replaced_ram = min(heads, key=lambda r: value[r.id]).name if heads else None
        replaced_ewe = (min(members[best_h], key=lambda e: value[e.id]).name
                        if best_h and len(members[best_h]) >= harem_ewes else None)
        ram_text = f"promote to {next((h for h, r in head_of.items() if r.name == replaced_ram), harems[0])}, replacing {replaced_ram}" \
            if heads else f"promote to {harems[0]}"
        ewe_text = f"promote to {best_h}" + (f", replacing {replaced_ewe}" if replaced_ewe else "")
        if a.sex == "M":
            verdict, reason = ("promote", ram_text) if as_ram else \
                ("keep", "only carrier of a Good copy") if last_carrier(a) else \
                ("cull" if lamb else "sell", "not better than the harem rams")
        elif a.sex == "F":
            verdict, reason = ("promote", ewe_text) if as_ewe else \
                ("keep", "only carrier of a Good copy") if last_carrier(a) else \
                ("keep", "spare ewe, nearly as good as the harems'") if v >= 0.9 * floor else \
                ("cull" if lamb else "sell", "not better than the harem ewes")
        else:  # unsexed lamb: horns show at maturity
            if as_ram or as_ewe:
                parts = ([f"if a ram: {ram_text}"] if as_ram else []) + ([f"if a ewe: {ewe_text}"] if as_ewe else [])
                verdict, reason = "promote", "; ".join(parts) + " (check horns when grown)"
            elif last_carrier(a):
                verdict, reason = "keep", "only carrier of a Good copy"
            else:
                verdict, reason = "cull", "no better than what the harems have, whatever its sex"
        verdicts[a.id] = {"verdict": verdict, "reason": reason}

    return {
        "pen": pen,
        "harems": {h: {"ram": head_of[h].id if h in head_of else None, "ewes": [e.id for e in members[h]]} for h in harems},
        "verdicts": verdicts,
        "value": {k: round(v, 3) for k, v in value.items()},
    }
