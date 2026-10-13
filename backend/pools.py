"""Pools mode: harems where each ram mates his ewes freely, plus a holding room ("Death Row").

The player doesn't arrange matings. They keep the best rams heading the harems, put each ewe with the ram she
complements best, and give every lamb a verdict - promote it into a harem, keep it in holding, cull it at birth, or
sell it once grown. Simulated on the test herd this reached a god male in ~8 h against ~9.4 h for hand-picked matings.

Everything here works on beliefs: expected Good copies per gene from inference (live mode) or from the captured rows
(test-server mode). Genes outside the target count as already Good/Good, so they never decide anything.
"""
from datetime import datetime, timezone
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


# Wool per shear by the card's Y (measured on the test server); an inbred animal produces a grade lower.
WOOL = {"G": 16, "O": 10, "B": 6}
WOOL_INBRED = {"G": 10, "O": 7, "B": 4}
Y, H, L = (genetics.GENES.index(g) for g in "YHL")


# Lifespan in hours by the card's L (published; +-10%). Inbred animals drop a grade, as for wool.
LIFESPAN_HOURS = {"G": 72.0, "O": 48.0, "B": 31.2}
LIFESPAN_INBRED_HOURS = {"G": 48.0, "O": 39.6, "B": 25.7}
RESERVE_HOURS_LEFT = 12  # a reserve animal with less life than this left is already being replaced
RESERVE_SIZE = 2  # production keeps this many god rams and god ewes alive, never sold or culled
RESERVE_MIN = 0.8  # ...each at least this likely Good/Good on every target gene


def god_chance(a, target: str, posterior: dict | None) -> float:
    """Chance of Good/Good on every target gene: from inference (live), or the captured rows (test server)."""
    p = 1.0
    for i, g in enumerate(genetics.GENES):
        if g not in target:
            continue
        if posterior is not None and a.id in posterior:
            p *= posterior[a.id][i].get("GG", 0.0)
        elif getattr(a, "genes_bottom", None):
            p *= float(a.genes_top[i] == "G" and a.genes_bottom[i] == "G")
        else:
            return 0.0
    return p


def lifespan_hours(a) -> float | None:
    return (LIFESPAN_INBRED_HOURS if getattr(a, "inbred", None) else LIFESPAN_HOURS).get(a.genes_top[L])


def hours_left(a, now) -> float | None:
    """Expected hours of life left (its age against its lifespan); None when the birth time isn't known."""
    born = getattr(a, "born_at", None)
    life = lifespan_hours(a)
    if born is None or life is None:
        return None
    if born.tzinfo is None:
        born = born.replace(tzinfo=timezone.utc)
    return life - (now - born).total_seconds() / 3600


def wool_per_shear(a) -> int:
    return (WOOL_INBRED if getattr(a, "inbred", None) else WOOL).get(a.genes_top[Y], 0)


def _markers(a):
    """The animal's two herd numbers as far as they're known: the one shown, and the hidden one (the same if the card
    says INBRED, otherwise unknown - None)."""
    shown = getattr(a, "herd_top", None)
    return shown, (shown if getattr(a, "inbred", None) else getattr(a, "herd_bottom", None))


def p_inbred_lamb(x, y) -> float:
    """Chance a lamb of x and y gets the same herd number from both (each passes one of its two at random). An unknown
    number matches a given one a quarter of the time - a rough allowance, as the herd shares a few numbers."""
    def same(m, n):
        if m is None or n is None:
            return 0.25
        return 1.0 if m == n else 0.0
    return sum(same(m, n) for m in _markers(x) for n in _markers(y)) / 4


def arrange(animals, target: str, posterior: dict | None, harems: list[str], holding, harem_ewes: int = 8,
            holding_size: int = 4, previous: set | None = None, harem_sizes: dict | None = None,
            holding_by_sex: dict | None = None, reject_room: str | None = None, goal: str = "god") -> dict:
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

    god_fit = fit
    reserve, short = set(), False
    if goal == "wool":
        # The god reserve: the best god rams and ewes, kept alive whatever their wool. Short of either sex, one breeding
        # room goes back to making god lambs (the best god pair) until the reserve is full again.
        chance = {a.id: god_chance(a, target, posterior) for a in animals}
        now = datetime.now(timezone.utc)

        def lasting(a):  # old age: one about to die can't be counted on
            left = hours_left(a, now)
            return left is None or left >= RESERVE_HOURS_LEFT
        for sex in "MF":
            best = sorted((a for a in grown if a.sex == sex and chance[a.id] >= RESERVE_MIN), key=lambda a: -chance[a.id])
            reserve |= {a.id for a in best[:RESERVE_SIZE]}  # kept while alive, even near the end
            best = [a for a in best if lasting(a)]
            short = short or len(best) < RESERVE_SIZE

    if goal == "wool":
        # Production: the god animals are done. Breed lambs that show green Y (full wool) and aren't inbred (a grade
        # less), with a little weight for green H (less feed) and L (longer life). Animals are valued by their own wool.
        def shows_good(ewe, ram, i):
            pe, pr = min(1.0, belief[ewe.id][i] / 2), min(1.0, belief[ram.id][i] / 2)  # chance each passes a Good copy
            return 1 - (1 - pe) * (1 - pr)

        def fit(ewe, ram):  # noqa: F811
            return (shows_good(ewe, ram, Y) * (1 - p_inbred_lamb(ewe, ram))
                    + 0.2 * shows_good(ewe, ram, H) + 0.1 * shows_good(ewe, ram, L))

        value = {a.id: wool_per_shear(a) / 16 + 0.05 * (a.genes_top[H] == "G") + 0.03 * (a.genes_top[L] == "G")
                 for a in animals}

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
            if short and males and females:  # reserve short: the first room breeds the best god pair
                _, r, e = max(((god_fit(e, r), r, e) for r in males for e in females if r.id != e.id),
                              key=lambda t: t[0])
                out.append((r, e))
                used |= {r.id, e.id}
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
        ram_text = f"breeds in {harem_of(weakest_ram) if weakest_ram else harems[0]}"
        ewe_text = f"breeds in {best_h}"
        if a.id in soon:
            # Its pair is settled when it's grown (the plan then lists it under its room): no partner named yet, as
            # the herd will have changed by then.
            verdict, reason = "promote", "breeding candidate once grown" + (" (check horns)" if a.sex == "?" else "")
        elif spare:
            verdict, reason = "keep", "spare for breeding"
        elif a.sex == "M":
            verdict, reason = ("promote", ram_text) if as_ram else                 ("keep", "only carrier of a Good copy") if last_carrier(a) else                 ("keep", "spare for breeding") if weakest_ram is not None and v >= 0.9 * value[weakest_ram.id] else                 ("cull" if lamb else "sell", "not useful for mating")
        elif a.sex == "F":
            verdict, reason = ("promote", ewe_text) if as_ewe else                 ("keep", "only carrier of a Good copy") if last_carrier(a) else                 ("keep", "spare for breeding") if v >= 0.9 * floor else                 ("cull" if lamb else "sell", "not useful for mating")
        else:  # unsexed lamb: horns show at maturity
            if as_ram or as_ewe:
                parts = ([f"if a ram: {ram_text}"] if as_ram else []) + ([f"if a ewe: {ewe_text}"] if as_ewe else [])
                verdict, reason = "promote", "; ".join(parts) + " (check horns when grown)"
            elif last_carrier(a):
                verdict, reason = "keep", "only carrier of a Good copy"
            else:
                verdict, reason = "cull", "not useful for mating"
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
                    verdicts[out.id] = {"verdict": "sell", "reason": "not useful for mating"}

    # A lamb not worth keeping is still worth selling once grown (an hour), so it only gets culled when holding has no
    # room to grow it. Best lambs get the free places first.
    places = max(1, holding_size) * len(holding_rooms)
    taken = sum(1 for a in animals if a.id in verdicts and verdicts[a.id]["verdict"] in ("promote", "keep", "sell"))
    unwanted = sorted((a for a in animals if verdicts.get(a.id, {}).get("verdict") == "cull"), key=lambda a: -value[a.id])
    for a in unwanted:
        if taken >= places:
            break
        verdicts[a.id] = {"verdict": "sell", "reason": "not useful for mating: sell once grown"}
        taken += 1

    # The vendor won't buy a pregnant ewe: a sale waits for the lamb.
    for a in animals:
        v = verdicts.get(a.id)
        if v and v["verdict"] == "sell" and getattr(a, "pregnant", False):
            v["reason"] += ": sell after she lambs"

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
                v["reason"] = "not useful for mating"
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

    if goal == "wool":
        # Good wool is worth keeping whether or not it breeds: only poor wool is surplus (the cull order ranks it).
        for a in animals:
            v = verdicts.get(a.id)
            if v and v["verdict"] in ("sell", "cull", "reject") and wool_per_shear(a) >= 16 and not getattr(a, "is_lamb", False):
                verdicts[a.id] = {"verdict": "keep", "reason": "wool producer: 16 per shear"}
                pen[a.id] = (holding_by_sex or {}).get(a.sex) or pen[a.id]

    if goal == "wool":
        for a in animals:  # the god reserve: never surplus, whatever its wool
            v = verdicts.get(a.id)
            if a.id in reserve and v is not None:
                verdicts[a.id] = {"verdict": "keep", "reason": f"god reserve ({chance[a.id]:.0%})"}
                pen[a.id] = (holding_by_sex or {}).get(a.sex) or pen[a.id]
            elif short and getattr(a, "is_lamb", False) and chance[a.id] >= RESERVE_MIN:
                verdicts[a.id] = {"verdict": "promote", "reason": f"god reserve candidate once grown ({chance[a.id]:.0%})"}

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
        "goal": goal,
        "reserve": sorted(reserve),
        "reserve_short": short,
    }


def safe_arrange(animals, target: str, posterior: dict | None, harems: list[str], holding, holding_by_sex: dict | None,
                 reject_room: str | None) -> dict:
    """Safe Mode, for when the player is away: nobody can breed and no room gets crowded.

    Every room holds one sex (lambs go with their own sex, so no son grows up beside his mother). The most valuable
    animals - god chance first, then wool - are spread out so one failure can't take them all: the top two rams share
    the first breeding room, the top two ewes the second, the next ram and ewe get the rams' and ewes' rooms to
    themselves, and the remaining rams go to the rejects room (the big one). Ewes left over have nowhere of their own:
    they share the ewes' room and are listed as overflow."""
    holding_rooms = [holding] if isinstance(holding, str) else list(holding)
    by_sex = holding_by_sex or {}
    chance = {a.id: god_chance(a, target, posterior) for a in animals}
    now = datetime.now(timezone.utc)

    def future(a):  # an animal with under a day to live is worth proportionally less to protect (Yuriy over Shelby 7)
        left = hours_left(a, now)
        return 1.0 if left is None else max(0.05, min(1.0, left / 24))
    value = {a.id: (chance[a.id] + 0.01 * wool_per_shear(a) / 16) * future(a) for a in animals}

    def ranked(sex):  # an unsexed lamb waits with the ewes
        return sorted((a for a in animals if a.sex == sex or (sex == "F" and a.sex == "?")), key=lambda a: -value[a.id])
    rams, ewes = ranked("M"), ranked("F")
    rooms = []  # (room, sex, places)
    if harems:
        rooms.append((harems[0], "M", 2))
    if len(harems) > 1:
        rooms.append((harems[1], "F", 2))
    if by_sex.get("M"):
        rooms.append((by_sex["M"], "M", 1))
    if by_sex.get("F"):
        rooms.append((by_sex["F"], "F", 1))
    pen, overflow = {}, []
    queue = {"M": list(rams), "F": list(ewes)}
    for room, sex, places in rooms:
        for a in queue[sex][:places]:
            pen[a.id] = room
        queue[sex] = queue[sex][places:]
    for a in queue["M"]:
        pen[a.id] = reject_room or by_sex.get("M") or (holding_rooms[0] if holding_rooms else "")
    for a in queue["F"]:
        pen[a.id] = by_sex.get("F") or (harems[1] if len(harems) > 1 else holding_rooms[0])
        overflow.append(a.id)
    verdicts = {a.id: {"verdict": "keep", "reason": "Safe Mode" + (" - check horns: kept with the ewes" if a.sex == "?" else "")}
                for a in animals}
    return {
        "holding_rooms": holding_rooms, "overflow": overflow, "pen": pen,
        "harems": {h: {"ram": None, "ewes": []} for h in harems},
        "verdicts": verdicts, "value": {k: round(v, 3) for k, v in value.items()},
        "goal": "safe", "safe_mode": True,
        "reserve": sorted(a.id for a in rams[:2] + ewes[:2] if chance[a.id] >= RESERVE_MIN), "reserve_short": False,
    }
