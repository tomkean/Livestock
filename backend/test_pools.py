"""Pools mode arrangement and verdicts. Run: python -m unittest test_pools"""
import unittest
from types import SimpleNamespace

import pools


def a(i, sex, top, bottom, lamb=False):
    return SimpleNamespace(id=i, name=f"a{i}", code=f"S-{i}", sex=sex, genes_top=top, genes_bottom=bottom, is_lamb=lamb)


class Pools(unittest.TestCase):
    def setUp(self):
        self.herd = [a(1, "M", "GGGGG", "GGOOO"), a(2, "M", "GOOOO", "OOOOO"), a(3, "M", "OOOOO", "OOOOO"),
                     a(4, "F", "GGGOO", "GOOOO"), a(5, "F", "OOOGG", "OOOGG"), a(6, "F", "OOOOO", "OOOOO")]

    def arrange(self, herd, ewes=8, holding_size=4):
        return pools.arrange(herd, "DLYFH", None, ["H1", "H2"], "Row", ewes, holding_size)

    def test_best_rams_head_the_harems_and_the_rest_wait(self):
        r = self.arrange(self.herd)
        self.assertEqual({r["harems"]["H1"]["ram"], r["harems"]["H2"]["ram"]}, {1, 2})
        self.assertEqual(r["pen"][3], "Row")
        self.assertEqual(r["verdicts"][3]["verdict"], "sell")

    def test_a_good_lamb_is_promoted_and_a_hopeless_one_grown_to_sell(self):
        herd = self.herd + [a(7, "?", "GGGGG", "GGGGG", lamb=True), a(8, "?", "BBBBB", "BBBBB", lamb=True)]
        r = self.arrange(herd, ewes=1)
        self.assertEqual(r["verdicts"][7]["verdict"], "promote")
        self.assertIn("once grown", r["verdicts"][7]["reason"])  # one-ewe rooms: pair mode
        self.assertIn("check horns", r["verdicts"][7]["reason"])
        self.assertEqual(r["verdicts"][8]["verdict"], "sell")

    def test_a_hopeless_lamb_is_culled_when_holding_is_full(self):
        herd = self.herd + [a(8, "?", "BBBBB", "BBBBB", lamb=True)]
        r = self.arrange(herd, ewes=1, holding_size=1)
        self.assertEqual(r["verdicts"][8]["verdict"], "cull")
        self.assertIn("full", r["verdicts"][8]["reason"])

    def test_two_lambs_never_replace_the_same_ewe(self):
        herd = self.herd + [a(7, "F", "GGGGG", "GGGGG", lamb=True), a(8, "F", "GGGGG", "GGGGO", lamb=True)]
        r = self.arrange(herd, ewes=1)
        replaced = [r["verdicts"][i]["reason"].split("replacing ")[-1] for i in (7, 8)
                    if r["verdicts"][i]["verdict"] == "promote" and "replacing" in r["verdicts"][i]["reason"]]
        self.assertEqual(len(replaced), len(set(replaced)))

    def test_animals_stay_in_their_harem_when_it_suits_them(self):
        herd = [a(1, "M", "GGGGG", "GGOOO"), a(2, "M", "GOOOO", "OOOOO"), a(4, "F", "GGGOO", "GOOOO")]
        herd[0].pen, herd[1].pen, herd[2].pen = "H2", "H1", "H1"
        r = self.arrange(herd)
        self.assertEqual(r["pen"][1], "H2")  # the best ram isn't moved just to head the first harem
        self.assertEqual(r["pen"][2], "H1")

    def test_a_promoted_ewe_lamb_grows_up_in_holding_then_joins_her_pair(self):
        # One-ewe rooms: a lamb in a breeding room would keep the ram out, so she waits until grown.
        herd = self.herd + [a(7, "F", "GGGGG", "GGGGG", lamb=True)]
        r = self.arrange(herd, ewes=1)
        self.assertEqual(r["verdicts"][7]["verdict"], "promote")
        self.assertIn("once grown", r["verdicts"][7]["reason"])
        self.assertEqual(r["pen"][7], "Row")
        self.assertTrue(all(len(h["ewes"]) <= 1 for h in r["harems"].values()))

    def test_pair_mode_gives_a_ewe_the_ram_that_completes_her(self):
        # The ewe has no Good Y. Ram 2 is worth more overall, but ram 1 is Good/Good on Y: the pair that can make a
        # god animal wins over the higher-valued ram.
        herd = [a(1, "M", "OGGOG", "BGGBB"), a(2, "M", "GGGGO", "GOOOB"), a(4, "F", "GGOGG", "GGBGG")]
        r = pools.arrange(herd, "DLYFH", None, ["VIP"], "Row", 1, 4)
        self.assertEqual(r["harems"]["VIP"]["ram"], 1)

    def test_holding_by_sex_puts_rams_and_ewes_in_their_own_rooms(self):
        herd = self.herd + [a(7, "?", "OOOOO", "OOOOO", lamb=True)]
        r = pools.arrange(herd, "DLYFH", None, ["VIP"], ["Gentlemen", "Ladies"], 1, 9,
                          holding_by_sex={"M": "Gentlemen", "F": "Ladies"})
        for x in herd:
            if r["pen"][x.id] in ("Gentlemen", "Ladies"):
                self.assertEqual(r["pen"][x.id], "Gentlemen" if x.sex == "M" else "Ladies")

    def test_unwanted_rams_go_to_rejects(self):
        r = pools.arrange(self.herd, "DLYFH", None, ["VIP"], ["Gentlemen", "Ladies", "Rejects"], 1, 9,
                          holding_by_sex={"M": "Gentlemen", "F": "Ladies"}, reject_room="Rejects")
        for x in self.herd:
            v = r["verdicts"].get(x.id)
            if x.sex == "M" and v and v["verdict"] == "reject":
                self.assertEqual(r["pen"][x.id], "Rejects")
            if v and v["verdict"] in ("sell", "cull"):
                self.assertNotEqual(x.sex, "M")  # rams are never sold or released straight off

    def test_harems_never_exceed_their_size(self):
        r = self.arrange(self.herd, ewes=1)
        self.assertTrue(all(len(h["ewes"]) <= 1 for h in r["harems"].values()))


if __name__ == "__main__":
    unittest.main()
