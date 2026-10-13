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
