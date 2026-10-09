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
        self.assertIn("if a ram", r["verdicts"][7]["reason"])
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

    def test_a_promoted_ewe_lamb_goes_straight_to_its_harem(self):
        herd = self.herd + [a(7, "F", "GGGGG", "GGGGG", lamb=True)]
        r = self.arrange(herd, ewes=1)
        self.assertEqual(r["verdicts"][7]["verdict"], "promote")
        self.assertIn(r["pen"][7], ("H1", "H2"))
        replaced = [i for i, v in r["verdicts"].items() if v["reason"].startswith("replaced in")]
        self.assertTrue(all(r["pen"][i] == "Row" for i in replaced))
        self.assertTrue(all(len(h["ewes"]) <= 1 for h in r["harems"].values()))

    def test_holding_by_sex_puts_rams_and_ewes_in_their_own_rooms(self):
        herd = self.herd + [a(7, "?", "OOOOO", "OOOOO", lamb=True)]
        r = pools.arrange(herd, "DLYFH", None, ["VIP"], ["Gentlemen", "Ladies"], 1, 9,
                          holding_by_sex={"M": "Gentlemen", "F": "Ladies"})
        for x in herd:
            if r["pen"][x.id] in ("Gentlemen", "Ladies"):
                self.assertEqual(r["pen"][x.id], "Gentlemen" if x.sex == "M" else "Ladies")

    def test_harems_never_exceed_their_size(self):
        r = self.arrange(self.herd, ewes=1)
        self.assertTrue(all(len(h["ewes"]) <= 1 for h in r["harems"].values()))


if __name__ == "__main__":
    unittest.main()
