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
NO_GOOD_PENALTY = 0.5  # value multiplier per target gene with no Good copy (a dead end for a god animal)
PREVIOUS_EDGE = 0.1  # the last plan's rams and promotions keep their place unless beaten by more than 10%
PAIR_MODE = True  # one-ewe rooms get whole pairs chosen (off only to compare against the old rule)


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
    # Good/Good counts extra: it is passed on every time. An animal with no Good copy at all of a target gene (its top
    # row shows O or B there) can never pass one on, so none of its lambs can be a god animal: that costs half its value
    # per missing gene, however strong it is elsewhere.
    total = sum(w * (c + max(0.0, c - 1)) for w, c in zip(weights, goods))
    return total * (NO_GOOD_PENALTY ** sum(1 for c in goods if c < 0.02))  # inference can leave a trace above 0


def arrange(animals, target: str, posterior: dict | None, harems: list[str], holding, harem_ewes: int = 8,
            holding_size: int = 4, previous: set | None = None, harem_sizes: dict | None = None,
            holding_by_sex: dict | None = None, reject_room: str | None = None) -> dict:
    """Suggested pen for every animal, plus a verdict and a reason for each one in holding.

    `holding` is one room name or a list of them; animals waiting there fill the rooms in order, `holding_size` each
    (best first, so the ones most worth keeping get a place and any overflow is the least valuable)."""
    holding_rooms = [holding] if isinstance(holding, str) else list(holding)
    harem_sizes = harem_sizes or {}

    def size(h):  # ewes a harem takes: the usual number, or its own (a one-ewe "honeymoon" room)
        return int(harem_sizes.get(h, harem_ewes))
    holding = holding_rooms[0]
    belief = beliefs(animals, target, posterior)
    weights = _weights(list(belief.values()))
    value = {a.id: _value(belief[a.id], weights) for a in animals}

    grown = [a for a in animals if not getattr(a, "is_lamb", False)]
    # The last plan's choices (harem rams, promoted lambs) get an edge, so a near-tie - two lambs whose estimates
    # drift by a percent as the herd changes - doesn't flip the advice back and forth.
    previous = previous or set()

    def held(a):
        return value[a.id] * (1 + PREVIOUS_EDGE if a.id in previous else 1)

    def ram_rank(a):
        return held(a) * (1 + STAY_MARGIN if getattr(a, "pen", "") in harems else 1)

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

    # Which ewes get harem places is decided by value; which harem each goes to, by fit - but a ewe already in a harem
    # stays put unless another suits her clearly better, and she settles in before newcomers are placed, so better
    # ewes don't push incumbents across to the other harem.
    ewes = sorted((a for a in grown if a.sex == "F"), key=lambda a: -value[a.id])
    chosen = ewes[:sum(size(h) for h in head_of)]

    def options_for(ewe):
        scores = {h: fit(ewe, head_of[h]) for h in head_of}
        options = sorted(head_of, key=lambda h: -scores[h])
        here = getattr(ewe, "pen", "")
        stays = here in scores and options and scores[options[0]] - scores[here] <= STAY_MARGIN * abs(scores[options[0]])
        if stays:
            options.remove(here)
            options.insert(0, here)  # nearly as good where she is: not worth a move
        return options, stays

    plans = {ewe.id: options_for(ewe) for ewe in chosen}
    for staying in (True, False):
        for ewe in chosen:
            options, stays = plans[ewe.id]
            if stays != staying or ewe.id in pen and pen[ewe.id] != holding:
                continue
            for h in options:
                if len(members[h]) < size(h):
                    members[h].append(ewe)
                    pen[ewe.id] = h
                    break

    # Pair mode: when every breeding room takes one ewe, choose whole pairs - the best pair first, by the chance of
    # its lambs (planner.pair_score) - rather than the best rams and then the best ewes for them. A great ewe needs
    # the ram that complements her, not just the highest-valued one. Lambs are paired too, as they'll be once grown:
    # a lamb that belongs in a better pair is told which, and takes its place when it grows up.
    pair_mode = PAIR_MODE and bool(harems) and all(size(h) == 1 for h in harems)
    soon = {}  # lamb id -> (room, partner, the animal it replaces)
    if pair_mode:
        def pair_value(r, e):
            here = getattr(r, "pen", "")
            together = here in harems and here == getattr(e, "pen", "")
            return fit(e, r) * (1 + PREVIOUS_EDGE if together else 1)  # a pair already together keeps a small edge

        def pick(males, females):
            options = sorted(((pair_value(r, e), r, e) for r in males for e in females if r.id != e.id),
                             key=lambda t: -t[0])
            out, used = [], set()
            for _, r, e in options:
                if len(out) == len(harems):
                    break
                if r.id not in used and e.id not in used:
                    out.append((r, e))
                    used |= {r.id, e.id}
            return out

        def rooms_for(pairs):
            placed, free = {}, list(harems)
            for r, e in pairs:  # a pair stays where one of them already is: fewer moves
                for here in (getattr(e, "pen", ""), getattr(r, "pen", "")):
                    if here in free:
                        placed[here] = (r, e)
                        free.remove(here)
                        break
            for pair in pairs:
                if pair not in placed.values():
                    placed[free.pop(0)] = pair
            return placed

        now_pairs = rooms_for(pick([a for a in grown if a.sex == "M"], [a for a in grown if a.sex == "F"]))
        pen = {a.id: holding for a in animals}
        head_of = {h: r for h, (r, _) in now_pairs.items()}
        members = {h: [] for h in harems}
        for h, (r, e) in now_pairs.items():
            members[h] = [e]
            pen[r.id] = pen[e.id] = h
        later = pick([a for a in animals if a.sex in ("M", "?")], [a for a in animals if a.sex in ("F", "?")])
        future = rooms_for(later)  # the rooms once the lambs are grown, so the notes agree with each other
        future_room = {x.id: h for h, pair in future.items() for x in pair}
        for h, (r, e) in future.items():
            for lamb, partner in ((r, e), (e, r)):
                if getattr(lamb, "is_lamb", False) and lamb.id not in soon:
                    now = now_pairs.get(h)
                    out = None if now is None else (now[0] if lamb is r else now[1])
                    soon[lamb.id] = (h, partner, out, future_room.get(out.id) if out is not None else None)

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
    for a in sorted((a for a in animals if pen[a.id] == holding), key=lambda a: -held(a)):
        v = held(a)
        # A challenger must beat the incumbent's standing, which includes its edge for already being in the harem.
        weakest_ram = min(heads, key=ram_rank) if heads else None
        as_ram = weakest_ram is None or v > ram_rank(weakest_ram)
        best_h = max(head_of, key=lambda h: fit(a, head_of[h])) if head_of else None
        weakest_ewe = min(members[best_h], key=ram_rank) if best_h and members[best_h] else None
        room = best_h is not None and len(members[best_h]) < size(best_h)
        as_ewe = best_h is not None and (room or (weakest_ewe is not None and v > ram_rank(weakest_ewe)))
        spare = pair_mode and (as_ram or as_ewe)  # good enough for a breeding room, just not in the best pairs now
        if pair_mode:
            as_ram = as_ewe = False  # the pairing above decided who breeds
        lamb = getattr(a, "is_lamb", False)
        ram_text = (f"promote to {harem_of(weakest_ram)}, replacing {weakest_ram.name}" if weakest_ram
                    else f"promote to {harems[0]}")
        ewe_text = f"promote to {best_h}" + ("" if room or weakest_ewe is None else f", replacing {weakest_ewe.name}")
        if a.id in soon:
            room, partner, out, out_to = soon[a.id]
            if out is None or out is partner:
                change = ""
            elif out_to is not None:
                change = f"; {out.name} moves to {out_to}"  # still breeding, in another pair
            else:
                change = f", replacing {out.name}"
            verdict, reason = "promote", (f"pair with {partner.name} in {room} once grown{change}" +
                                          (" (check horns)" if a.sex == "?" else ""))
        elif spare:
            verdict, reason = "keep", "good enough to breed: waits for a place in a pair"
        elif a.sex == "M":
            verdict, reason = ("promote", ram_text) if as_ram else                 ("keep", "only carrier of a Good copy") if last_carrier(a) else                 ("keep", "spare ram, nearly as good as the harem rams") if weakest_ram is not None and v >= 0.9 * value[weakest_ram.id] else                 ("cull" if lamb else "sell", "not better than the harem rams")
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
        now_in = getattr(a, "pen", "")
        if now_in in harems and verdict != "promote":
            # It's in a harem today but the plan has no place for it there.
            places = sum(size(h) for h in harems) if a.sex == "F" else len(harems)
            kind = "ewes" if a.sex == "F" else "rams"
            reason = f"out of {now_in}: {places} better {kind} fill the harem places" +                 (f" - but keep it: {reason}" if verdict == "keep" else "")
        verdicts[a.id] = {"verdict": verdict, "reason": reason}
        if verdict == "promote" and not pair_mode:  # it takes the place it was promised (both, for an unsexed lamb)
            out, goes_to = None, None
            if as_ram and a.sex in ("M", "?") and weakest_ram is not None:
                heads[heads.index(weakest_ram)] = a
                ram_home[a.id] = ram_home.get(weakest_ram.id, harems[0])
                if a.sex == "M":
                    out, goes_to = weakest_ram, ram_home[a.id]
            if as_ewe and a.sex in ("F", "?"):
                if not room and weakest_ewe is not None:
                    members[best_h].remove(weakest_ewe)
                members[best_h].append(a)
                if a.sex == "F" or not as_ram:  # an unsexed lamb only goes ahead if it has just the one place
                    out, goes_to = (None if room else weakest_ewe), best_h
            # Straight to its new harem, no stop in holding; whoever it replaces moves out to holding instead.
            if goes_to:
                pen[a.id] = goes_to
                if out is not None and pen.get(out.id) != holding:
                    pen[out.id] = holding
                    verdicts[out.id] = {"verdict": "sell", "reason": f"replaced in {goes_to} by {a.name}"}

    # A lamb not worth keeping is still worth selling once grown (an hour), so it only gets culled when holding has no
    # room to grow it. Best lambs get the free places first.
    places = max(1, holding_size) * len(holding_rooms)
    taken = sum(1 for a in animals if a.id in verdicts and verdicts[a.id]["verdict"] in ("promote", "keep", "sell"))
    unwanted = sorted((a for a in animals if verdicts.get(a.id, {}).get("verdict") == "cull"), key=lambda a: -value[a.id])
    for a in unwanted:
        if taken >= places:
            break
        verdicts[a.id] = {"verdict": "sell", "reason": "not needed for breeding: grow it in {room} for an hour, then sell"}
        taken += 1
    for a in unwanted:
        if verdicts[a.id]["verdict"] == "cull":
            verdicts[a.id]["reason"] += " - and {room} is full"

    # The vendor won't buy a pregnant ewe: a sale waits for the lamb.
    for a in animals:
        v = verdicts.get(a.id)
        if v and v["verdict"] == "sell" and getattr(a, "pregnant", False):
            v["reason"] += " - after she lambs (the vendor won't buy a pregnant ewe)"

    # Spread the animals waiting in holding across the holding rooms, most valuable first.
    order = {"promote": 0, "keep": 1, "sell": 2, "reject": 2, "cull": 3}
    waiting = sorted((a for a in animals if pen[a.id] == holding),
                     key=lambda a: (order[verdicts[a.id]["verdict"]], -value[a.id]))
    overflow = []
    if reject_room:
        # Rams the plan has no use for go to a rejects room rather than the barn or a release: still worth their wool,
        # and sold when it's safe to take them.
        for a in waiting:
            v = verdicts.get(a.id)
            if a.sex == "M" and v and v["verdict"] in ("sell", "cull"):
                v["verdict"] = "reject"
                if a in unwanted:  # a lamb: its own note was about growing it in holding, which no longer applies
                    v["reason"] = f"not needed for breeding: grow it in {reject_room}, keep it for wool, sell when the barn is quiet"
                else:
                    v["reason"] = f"{v['reason']} - keep for wool in {reject_room}, sell when the barn is quiet"
                pen[a.id] = reject_room
        waiting = [a for a in waiting if pen[a.id] != reject_room]
    if holding_by_sex:
        # Separate rooms for rams and ewes ("Gentlemen" / "Ladies"): no unplanned matings while they wait, and the
        # ewes are calmer to shear. Unsexed lambs wait with the ewes until their horns show.
        filled = {}
        for a in waiting:
            room = holding_by_sex.get(a.sex) or holding_by_sex.get("F") or holding_rooms[0]
            pen[a.id] = room
            filled[room] = filled.get(room, 0) + 1
            if filled[room] > holding_size:
                overflow.append(a.id)
        waiting = []
    for k, a in enumerate(waiting):
        room = k // max(1, holding_size)
        if room < len(holding_rooms):
            pen[a.id] = holding_rooms[room]
        else:
            pen[a.id] = holding_rooms[-1]
            overflow.append(a.id)

    # Notes about growing a lamb name the room it is actually given (its own sex's room, not the first holding room).
    for a in animals:
        v = verdicts.get(a.id)
        if v and "{room}" in v["reason"]:
            v["reason"] = v["reason"].replace("{room}", pen[a.id])

    return {
        "holding_rooms": holding_rooms,
        "overflow": overflow,
        "pen": pen,
        "harems": {h: {"ram": head_of[h].id if h in head_of else None, "ewes": [e.id for e in members[h]]} for h in harems},
        "verdicts": verdicts,
        "value": {k: round(v, 3) for k, v in value.items()},
    }
