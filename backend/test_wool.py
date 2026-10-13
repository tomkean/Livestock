"""Production (wool) goal: pairs for green-Y, non-inbred lambs; a god reserve kept alive."""
from types import SimpleNamespace

import pools


def a(i, sex, top, bottom, herd, inbred, lamb=False):
    return SimpleNamespace(id=i, name=f"a{i}", code=f"S-{i}", sex=sex, genes_top=top, genes_bottom=bottom,
                           herd_top=herd, herd_bottom=herd if inbred else None, inbred=inbred, is_lamb=lamb, pen="")


def plan(herd, rooms=("VIP",)):
    return pools.arrange(herd, "LYFH", None, list(rooms), ["Gentlemen", "Ladies"], 1, 9,
                         holding_by_sex={"M": "Gentlemen", "F": "Ladies"}, goal="wool")


def test_an_inbred_god_ewe_gets_a_ram_with_another_herd_number():
    gods = [a(1, "M", "OGGGG", "OGGGG", 3, True), a(4, "M", "OGGGG", "OGGGG", 3, True),
            a(3, "F", "OGGGG", "OGGGG", 3, True), a(6, "F", "OGGGG", "OGGGG", 3, True)]  # a full reserve
    r = plan(gods + [a(2, "M", "OGGGG", "OOOOO", 0, False)])
    assert not r["reserve_short"]
    assert r["harems"]["VIP"]["ram"] == 2  # a 3/3 x 3/3 lamb is always inbred: 10 wool, not 16


def test_the_god_reserve_is_never_surplus():
    herd = [a(1, "M", "OGGGG", "OGGGG", 3, True), a(2, "M", "OGGGG", "OGGGG", 3, True),
            a(3, "F", "OGGGG", "OGGGG", 3, True), a(4, "F", "OGGGG", "OGGGG", 3, True),
            a(5, "M", "OGGGG", "OOOOO", 0, False)]
    r = plan(herd)
    assert set(r["reserve"]) == {1, 2, 3, 4} and not r["reserve_short"]
    for i in (1, 2, 3, 4):
        v = r["verdicts"].get(i)
        assert v is None or v["verdict"] in ("keep", "promote")


def test_a_short_reserve_breeds_the_best_god_pair():
    herd = [a(1, "M", "OGGGG", "OGGGG", 3, True), a(2, "M", "OGGGG", "OOOOO", 0, False),
            a(3, "F", "OGGGG", "OGGGG", 3, True)]
    r = plan(herd, rooms=("VIP", "VIP 2"))
    assert r["reserve_short"]
    pairs = {(h["ram"], tuple(h["ewes"])) for h in r["harems"].values()}
    assert (1, (3,)) in pairs  # one room makes god lambs to refill the reserve


def test_safe_mode_keeps_every_room_single_sex_and_spreads_the_best():
    herd = [a(1, "M", "OGGGG", "OGGGG", 3, True), a(2, "M", "OGGGG", "OGGGG", 3, True), a(3, "M", "OGGGG", "OOOOO", 0, False),
            a(5, "M", "OOOOO", "OOOOO", 0, False), a(4, "F", "OGGGG", "OGGGG", 3, True), a(6, "F", "OGGGG", "OGGGG", 3, True),
            a(7, "F", "OGGGG", "OOOOO", 0, False), a(8, "M", "OGGGG", "OGGGG", 3, True, lamb=True)]
    r = pools.safe_arrange(herd, "LYFH", None, ["VIP", "VIP 2"], ["Gentlemen", "Ladies", "Rejects"],
                           {"M": "Gentlemen", "F": "Ladies"}, "Rejects")
    sexes = {}
    for x in herd:
        sexes.setdefault(r["pen"][x.id], set()).add(x.sex)
    assert all(len(s) == 1 for s in sexes.values())  # no room with both sexes: no breeding
    assert not any(h["ram"] for h in r["harems"].values())
    assert {r["pen"][1], r["pen"][2]} == {"VIP"} and {r["pen"][4], r["pen"][6]} == {"VIP 2"}


def test_rooms_hold_one_sex_within_capacity():
    rooms = [{"name": "VIP", "capacity": 3}, {"name": "VIP 2", "capacity": 3}, {"name": "Gents", "capacity": 1},
             {"name": "Ladies", "capacity": 1}, {"name": "Big", "capacity": 5}]
    assert pools.breeding_rooms(rooms) == ["VIP", "VIP 2"]  # the biggest is kept for the flock
    herd = [a(i, "M" if i < 6 else "F", "OGGGG", "OGGGG", 3, True) for i in range(1, 12)]
    value = {x.id: 1.0 - x.id / 100 for x in herd}
    pen, overflow = pools.place_in_rooms(herd, rooms, {"VIP": [1, 6]}, value)
    assert pen[1] == pen[6] == "VIP"
    counts, sexes = {}, {}
    for x in herd:
        counts[pen[x.id]] = counts.get(pen[x.id], 0) + 1
        sexes.setdefault(pen[x.id], set()).add(x.sex)
    caps = {r["name"]: r["capacity"] for r in rooms}
    assert all(counts[r] <= caps[r] for r in counts if r)
    assert all(len(s) == 1 for r, s in sexes.items() if r != "VIP")
    assert sum(1 for x in herd if x.id not in overflow) <= sum(caps.values())
