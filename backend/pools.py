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
# Moving sheep is work (and each new lamb shifts which genes are scarce), so the plan only moves an animal for a clear
# gain: a ewe stays in her harem unless another suits her 50% better, a heading ram keeps his harem unless a challenger
# is worth 50% more.
STAY_MARGIN = 0.5


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


def arrange(animals, target: str, posterior: dict | None, harems: list[str], holding, harem_ewes: int = 8,
            holding_size: int = 4) -> dict:
    """Suggested pen for every animal, plus a verdict and a reason for each one in holding.

    `holding` is one room name or a list of them; animals waiting there fill the rooms in order, `holding_size` each
    (best first, so the ones most worth keeping get a place and any overflow is the least valuable)."""
    holding_rooms = [holding] if isinstance(holding, str) else list(holding)
    holding = holding_rooms[0]
    belief = beliefs(animals, target, posterior)
    weights = _weights(list(belief.values()))
    value = {a.id: _value(belief[a.id], weights) for a in animals}

    grown = [a for a in animals if not getattr(a, "is_lamb", False)]
    def ram_rank(a):
        return value[a.id] * (1 + STAY_MARGIN if getattr(a, "pen", "") in harems else 1)

    rams = sorted((a for a in grown if a.sex == "M"), key=lambda a: -ram_rank(a))
    heads = rams[:len(harems)]
    pen = {a.id: holding for a in animals}
    members = {h: [] for h in harems}
    # A chosen ram stays in the harem he's already in; the others fill the harems left without one.
    head_of = {}
    for ram in heads:
        here = getattr(ram, "pen", "")
        if here in members and here not in head_of:
            head_of[here] = ram
    for ram in heads:
        if ram not in head_of.values():
            head_of[next(h for h in harems if h not in head_of)] = ram
    for name, ram in head_of.items():
        pen[ram.id] = name

    def fit(ewe, ram):
        return planner.pair_score(_beast(ewe, belief[ewe.id]), _beast(ram, belief[ram.id]),
                                  [_beast(x, belief[x.id]) for x in animals], weights)

    ewes = sorted((a for a in grown if a.sex == "F"), key=lambda a: -value[a.id])
    for ewe in ewes:
        scores = {h: fit(ewe, head_of[h]) for h in head_of}
        options = sorted(head_of, key=lambda h: -scores[h])
        here = getattr(ewe, "pen", "")
        if here in scores and options and scores[options[0]] - scores[here] <= STAY_MARGIN * abs(scores[options[0]]):
            options.remove(here)
            options.insert(0, here)  # nearly as good where she is: not worth a move
        for h in options:
            if len(members[h]) < harem_ewes:
                members[h].append(ewe)
                pen[ewe.id] = h
                break

    # Verdicts for everything in holding, best first: each promotion takes its place in the harems before the next
    # animal is judged, so two lambs are never both told to replace the same ewe.
    members = {h: list(m) for h, m in members.items()}
    heads = list(head_of.values())
    kept_values = [value[a.id] for a in animals if pen[a.id] != holding]
    floor = min(kept_values) if kept_values else 0.0

    def last_carrier(a):
        return any(belief[a.id][i] > 0.5 and not any(o.id != a.id and belief[o.id][i] > 0.5 for o in animals)
                   for i in range(N))

    ram_home = {r.id: h for h, r in head_of.items()}

    def harem_of(ram):
        return ram_home.get(ram.id, harems[0])

    verdicts = {}
    for a in sorted((a for a in animals if pen[a.id] == holding), key=lambda a: -value[a.id]):
        v = value[a.id]
        weakest_ram = min(heads, key=lambda r: value[r.id]) if heads else None
        as_ram = weakest_ram is None or v > value[weakest_ram.id]
        best_h = max(head_of, key=lambda h: fit(a, head_of[h])) if head_of else None
        weakest_ewe = min(members[best_h], key=lambda e: value[e.id]) if best_h and members[best_h] else None
        room = best_h is not None and len(members[best_h]) < harem_ewes
        as_ewe = best_h is not None and (room or (weakest_ewe is not None and v > value[weakest_ewe.id]))
        lamb = getattr(a, "is_lamb", False)
        ram_text = (f"promote to {harem_of(weakest_ram)}, replacing {weakest_ram.name}" if weakest_ram
                    else f"promote to {harems[0]}")
        ewe_text = f"promote to {best_h}" + ("" if room or weakest_ewe is None else f", replacing {weakest_ewe.name}")
        if a.sex == "M":
            verdict, reason = ("promote", ram_text) if as_ram else                 ("keep", "only carrier of a Good copy") if last_carrier(a) else                 ("cull" if lamb else "sell", "not better than the harem rams")
        elif a.sex == "F":
            verdict, reason = ("promote", ewe_text) if as_ewe else                 ("keep", "only carrier of a Good copy") if last_carrier(a) else                 ("keep", "spare ewe, nearly as good as the harems'") if v >= 0.9 * floor else                 ("cull" if lamb else "sell", "not better than the harem ewes")
        else:  # unsexed lamb: horns show at maturity
            if as_ram or as_ewe:
                parts = ([f"if a ram: {ram_text}"] if as_ram else []) + ([f"if a ewe: {ewe_text}"] if as_ewe else [])
                verdict, reason = "promote", "; ".join(parts) + " (check horns when grown)"
            elif last_carrier(a):
                verdict, reason = "keep", "only carrier of a Good copy"
            else:
                verdict, reason = "cull", "no better than what the harems have, whatever its sex"
        verdicts[a.id] = {"verdict": verdict, "reason": reason}
        if verdict == "promote":  # it takes the place it was promised (both, for an unsexed lamb)
            if as_ram and a.sex in ("M", "?") and weakest_ram is not None:
                heads[heads.index(weakest_ram)] = a
                ram_home[a.id] = ram_home.get(weakest_ram.id, harems[0])
            if as_ewe and a.sex in ("F", "?"):
                if not room and weakest_ewe is not None:
                    members[best_h].remove(weakest_ewe)
                members[best_h].append(a)

    # A lamb not worth keeping is still worth selling once grown (an hour), so it only gets culled when holding has no
    # room to grow it. Best lambs get the free places first.
    places = max(1, holding_size) * len(holding_rooms)
    taken = sum(1 for a in animals if a.id in verdicts and verdicts[a.id]["verdict"] in ("promote", "keep", "sell"))
    unwanted = sorted((a for a in animals if verdicts.get(a.id, {}).get("verdict") == "cull"), key=lambda a: -value[a.id])
    for a in unwanted:
        if taken >= places:
            break
        verdicts[a.id] = {"verdict": "sell", "reason": f"not needed for breeding: grow it in {holding_rooms[0]} for an hour, then sell"}
        taken += 1
    for a in unwanted:
        if verdicts[a.id]["verdict"] == "cull":
            verdicts[a.id]["reason"] += f" - and {holding_rooms[0]} is full"

    # Spread the animals waiting in holding across the holding rooms, most valuable first.
    order = {"promote": 0, "keep": 1, "sell": 2, "cull": 3}
    waiting = sorted((a for a in animals if pen[a.id] == holding),
                     key=lambda a: (order[verdicts[a.id]["verdict"]], -value[a.id]))
    overflow = []
    for k, a in enumerate(waiting):
        room = k // max(1, holding_size)
        if room < len(holding_rooms):
            pen[a.id] = holding_rooms[room]
        else:
            pen[a.id] = holding_rooms[-1]
            overflow.append(a.id)

    return {
        "holding_rooms": holding_rooms,
        "overflow": overflow,
        "pen": pen,
        "harems": {h: {"ram": head_of[h].id if h in head_of else None, "ewes": [e.id for e in members[h]]} for h in harems},
        "verdicts": verdicts,
        "value": {k: round(v, 3) for k, v in value.items()},
    }
