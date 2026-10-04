"""Checks the mating odds against cases worked out by hand. Run: python -m unittest test_genetics"""
import unittest
from types import SimpleNamespace

import genetics


def sheep(top, bottom, herd_top, herd_bottom):
    return SimpleNamespace(genes_top=top, genes_bottom=bottom, herd_top=herd_top, herd_bottom=herd_bottom)


# Test server animals, 2026-10-04 (MECHANICS.md observation log). Rows in D L Y F H order.
TAYLOR = sheep("OOGGG", "BBGBG", 15, 12)
BRENDA = sheep("OGGOB", "OBOBB", 14, 4)
ESTELLA = sheep("GBGOO", "BBOBO", 6, 0)


class MatingOdds(unittest.TestCase):
    def expressed(self, odds):
        return {g["gene"]: {k: round(v, 4) for k, v in g["expressed"].items() if v} for g in odds["genes"]}

    def test_taylor_brenda(self):
        odds = genetics.mating_odds(BRENDA, TAYLOR)
        self.assertEqual(self.expressed(odds), {
            "D": {"O": 1.0},
            "L": {"G": 0.5, "O": 0.25, "B": 0.25},
            "Y": {"G": 1.0},
            "F": {"G": 0.5, "O": 0.25, "B": 0.25},
            "H": {"G": 1.0},
        })
        self.assertEqual(odds["genes"][4]["genotypes"], {"GB": 1.0})  # H always Good over Bad
        self.assertEqual(odds["p_inbred"], 0.0)
        self.assertEqual(odds["p_god_male"], 0.0)  # nobody carries a Good D
        self.assertTrue(odds["rows_known"] and odds["markers_known"])

    def test_first_birth_was_possible(self):
        # Brenda junior, born 2026-10-04: every gene the model said she could have.
        lamb = sheep("OGGBG", "BBGBB", 14, 15)
        odds = genetics.mating_odds(BRENDA, TAYLOR)
        for i, g in enumerate(odds["genes"]):
            pair = lamb.genes_top[i] + lamb.genes_bottom[i]
            self.assertGreater(g["genotypes"].get(pair, 0), 0, g["gene"])
        self.assertIn(lamb.herd_top, (BRENDA.herd_top, BRENDA.herd_bottom))
        self.assertIn(lamb.herd_bottom, (TAYLOR.herd_top, TAYLOR.herd_bottom))

    def test_second_birth_was_possible(self):
        # Elsie junior, born 2026-10-04 to inbred Elsie (12/12) and Santos.
        elsie = sheep("OOGGG", "OBOOB", 12, 12)
        santos = sheep("OOOOO", "BOBOO", 11, 15)
        lamb = sheep("OOGGG", "OOOOO", 12, 15)
        odds = genetics.mating_odds(elsie, santos)
        for i, g in enumerate(odds["genes"]):
            pair = lamb.genes_top[i] + lamb.genes_bottom[i]
            self.assertGreater(g["genotypes"].get(pair, 0), 0, g["gene"])
        self.assertEqual(odds["p_inbred"], 0.0)

    def test_taylor_estella(self):
        odds = genetics.mating_odds(ESTELLA, TAYLOR)
        self.assertEqual(self.expressed(odds), {
            "D": {"G": 0.5, "O": 0.25, "B": 0.25},
            "L": {"O": 0.5, "B": 0.5},
            "Y": {"G": 1.0},
            "F": {"G": 0.5, "O": 0.25, "B": 0.25},
            "H": {"G": 1.0},
        })
        self.assertEqual(odds["p_all_good"], 0.0)  # L can never be Good

    def test_inbred_when_markers_shared(self):
        # One shared marker: the offspring is inbred only when both parents pass it.
        a = sheep("GGGGG", "GGGGG", 5, 7)
        b = sheep("GGGGG", "GGGGG", 5, 9)
        self.assertEqual(genetics.mating_odds(a, b)["p_inbred"], 0.25)
        # An inbred parent (5/5) passes 5 every time.
        c = sheep("GGGGG", "GGGGG", 5, 5)
        self.assertEqual(genetics.mating_odds(c, b)["p_inbred"], 0.5)
        self.assertEqual(genetics.mating_odds(a, b)["p_god_male"], 0.5)

    def test_unknown_second_row_uses_prior(self):
        # Good on top with nothing known underneath: G, O or B equally likely.
        self.assertEqual(genetics.gene_genotypes("G", None), {"GG": 1 / 3, "GO": 1 / 3, "GB": 1 / 3})
        self.assertEqual(genetics.gene_genotypes("B", None), {"BB": 1.0})
        unknown = sheep("GGGGG", None, 1, None)
        odds = genetics.mating_odds(unknown, TAYLOR)
        self.assertFalse(odds["rows_known"])
        self.assertFalse(odds["markers_known"])


if __name__ == "__main__":
    unittest.main()
