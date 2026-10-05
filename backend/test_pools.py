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

    def arrange(self, herd, ewes=8):
        return pools.arrange(herd, "DLYFH", None, ["H1", "H2"], "Row", ewes)

    def test_best_rams_head_the_harems_and_the_rest_wait(self):
        r = self.arrange(self.herd)
        self.assertEqual({r["harems"]["H1"]["ram"], r["harems"]["H2"]["ram"]}, {1, 2})
        self.assertEqual(r["pen"][3], "Row")
        self.assertEqual(r["verdicts"][3]["verdict"], "sell")

    def test_a_good_lamb_is_promoted_and_a_hopeless_one_culled(self):
        herd = self.herd + [a(7, "?", "GGGGG", "GGGGG", lamb=True), a(8, "?", "BBBBB", "BBBBB", lamb=True)]
        r = self.arrange(herd, ewes=1)
        self.assertEqual(r["verdicts"][7]["verdict"], "promote")
        self.assertIn("if a ram", r["verdicts"][7]["reason"])
        self.assertEqual(r["verdicts"][8]["verdict"], "cull")

    def test_harems_never_exceed_their_size(self):
        r = self.arrange(self.herd, ewes=1)
        self.assertTrue(all(len(h["ewes"]) <= 1 for h in r["harems"].values()))


if __name__ == "__main__":
    unittest.main()
