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

    def test_parent_finder_names_the_real_parents(self):
        # Dale: Taylor's lamb by Elsie or Nettie (worked out by hand); no other recorded pairing fits.
        def ewe(id, top, bottom, a, b):
            return SimpleNamespace(id=id, species="sheep", sex="F", genes_top=top, genes_bottom=bottom, herd_top=a, herd_bottom=b)
        def ram(id, top, bottom, a, b):
            return SimpleNamespace(id=id, species="sheep", sex="M", genes_top=top, genes_bottom=bottom, herd_top=a, herd_bottom=b)
        herd = [ewe(1, "OOGGG", "OBOOB", 12, 12), ewe(2, "GOGGG", "OBOOB", 13, 15), ewe(3, "GGGOO", "OOOOO", 4, 15),
                ewe(4, "OGGBG", "BBGBB", 14, 15), ram(10, "OOGGG", "BBGBG", 15, 12), ram(11, "OGGBO", "BGOBO", 15, 0)]
        dale = SimpleNamespace(id=99, species="sheep", genes_top="OOGOG", genes_bottom="OOOBG", herd_top=12, herd_bottom=15)
        found = genetics.likely_parents(dale, herd)
        self.assertEqual({(p["mother_id"], p["father_id"]) for p in found}, {(1, 10), (2, 10)})
        # A recorded mating tips the balance.
        found = genetics.likely_parents(dale, herd, mated_pairs={(2, 10)})
        self.assertEqual((found[0]["mother_id"], found[0]["father_id"]), (2, 10))
        # So does where they were: Elsie was in Taylor's harem when the lamb was conceived, Nettie wasn't.
        pens = {1: "H1", 2: "H2", 10: "H1", 11: "H2"}
        found = genetics.likely_parents(dale, herd, places=lambda m, f: (pens.get(m.id) == pens.get(f.id), True))
        self.assertEqual((found[0]["mother_id"], found[0]["father_id"]), (1, 10))
        self.assertTrue(found[0]["together"])
        self.assertGreater(found[0]["chance"], 0.9)

    def test_parent_finder_skips_parents_too_young(self):
        from datetime import datetime, timedelta, timezone
        t = datetime(2026, 10, 5, 1, 0, tzinfo=timezone.utc)
        ewe = SimpleNamespace(id=1, species="sheep", sex="F", genes_top="GGGGG", genes_bottom="GGGGG", herd_top=1, herd_bottom=2, born_at=t)
        ram = SimpleNamespace(id=2, species="sheep", sex="M", genes_top="GGGGG", genes_bottom="GGGGG", herd_top=3, herd_bottom=4, born_at=None)
        lamb = SimpleNamespace(id=3, species="sheep", genes_top="GGGGG", genes_bottom="GGGGG", herd_top=1, herd_bottom=3,
                               born_at=t + timedelta(minutes=30))
        self.assertEqual(genetics.likely_parents(lamb, [ewe, ram]), [])  # the ewe was 30 minutes old
        lamb.born_at = t + timedelta(minutes=75)
        self.assertEqual(len(genetics.likely_parents(lamb, [ewe, ram])), 1)

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
        # Good on top with nothing known underneath: weighted by the wild odds (Good 20%, Ok 50%, Bad 30%).
        dist = genetics.gene_genotypes("G", None)
        self.assertAlmostEqual(dist["GG"], 0.04 / 0.36)
        self.assertAlmostEqual(dist["GO"], 0.20 / 0.36)
        self.assertAlmostEqual(dist["GB"], 0.12 / 0.36)
        self.assertEqual(genetics.gene_genotypes("B", None), {"BB": 1.0})
        unknown = sheep("GGGGG", None, 1, None)
        odds = genetics.mating_odds(unknown, TAYLOR)
        self.assertFalse(odds["rows_known"])
        self.assertFalse(odds["markers_known"])


if __name__ == "__main__":
    unittest.main()
