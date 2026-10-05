"""Basic promises of the breeding planner. Run: python -m unittest test_planner"""
import random
import unittest
from types import SimpleNamespace

import planner


def animal(id, sex, top, bottom, markers=(1, 2), origin="ranch"):
    return SimpleNamespace(id=id, sex=sex, genes_top=top, genes_bottom=bottom, herd_top=markers[0],
                           herd_bottom=markers[1], origin=origin, pregnant=False, name=f"a{id}", code=f"S-{id:02d}",
                           age_minutes=None)


class Planner(unittest.TestCase):
    def test_impossible_when_a_gene_has_no_good_copy(self):
        herd = [animal(1, "F", "GGGGO", "GGGGO"), animal(2, "M", "GGGGO", "OOOOO", (3, 4))]
        result = planner.plan(herd, runs=20)
        self.assertFalse(result["possible"])
        self.assertEqual(result["missing"], ["H"])

    def test_god_pair_gives_a_god_male_on_the_first_births(self):
        herd = [animal(1, "F", "GGGGG", "GGGGG"), animal(2, "M", "GGGGG", "GGGGG", (3, 4))]
        outcome = planner.simulate(planner.herd_from_animals(herd, 0, random.Random(1)), random.Random(1))
        # Every lamb is a god animal, so the first male born is the answer: a birth or two after 10 minutes.
        self.assertIsNotNone(outcome.god_at)
        self.assertLess(outcome.god_at, 3 * 60)

    def test_scattered_good_copies_still_reach_a_god_male(self):
        # Each gene's Good copies sit in different animals, as in the test-server herd.
        herd = [animal(1, "F", "GOOOO", "BOOOO", (1, 2)), animal(2, "F", "OGOOO", "OBOOO", (3, 4)),
                animal(3, "F", "OOGOO", "OOBOO", (5, 6)), animal(4, "M", "OOOGO", "OOOBO", (7, 8)),
                animal(5, "M", "OOOOG", "OOOOB", (9, 10))]
        result = planner.plan(herd, runs=60)
        self.assertTrue(result["possible"])
        self.assertGreater(result["expected"]["success"], 0.5)
        self.assertTrue(result["matings"])


    def test_trip_keeps_last_carriers_and_respects_the_truck(self):
        def a(i, sex, top, lamb=False):
            return SimpleNamespace(id=i, sex=sex, genes_top=top, genes_bottom=None, name=f"a{i}", code=f"S-{i}", is_lamb=lamb)
        herd = [a(1, "M", "OOGGG"), a(2, "M", "OGOOO"), a(3, "M", "OOOOO"), a(4, "F", "GOOOO")]
        trip = planner.trip_plan(herd, "sheep", "double", {"F": 8})
        self.assertEqual([s["id"] for s in trip["sell"]], [3])  # ram 2 is the only one showing green L
        self.assertEqual(trip["buy"], ["F", "F"])
        self.assertEqual(planner.trip_plan([], "sheep", "single", {"F": 8})["buy"], ["M"])
        cows = planner.trip_plan(herd, "cow", "single", {"F": 8})
        self.assertEqual((cows["sell"], cows["buy"]), ([], ["F"]))  # a single module can't carry a grown cow


    def test_trip_skips_a_pregnant_ewe_for_the_next_weakest(self):
        def a(i, sex, top, pregnant=False):
            return SimpleNamespace(id=i, sex=sex, genes_top=top, genes_bottom=None, name=f"a{i}", code=f"S-{i}",
                                   is_lamb=False, pregnant=pregnant)
        herd = [a(1, "M", "GGGGG"), a(2, "F", "GGGGO"), a(3, "F", "GOOOO"), a(4, "F", "OOOOO", pregnant=True)]
        trip = planner.trip_plan(herd, "sheep", "double", {"F": 2})
        self.assertEqual([s["id"] for s in trip["sell"]], [3])


    def test_ignored_genes_dont_block_the_plan(self):
        # Nobody carries a Good H, so a full god male is impossible - but not if H is left out of the target.
        herd = [animal(1, "F", "GGGGO", "GGGGO"), animal(2, "M", "GGGGO", "OOOOO", (3, 4))]
        self.assertFalse(planner.plan(herd, runs=10)["possible"])
        result = planner.plan(herd, runs=30, target="DLYF")
        self.assertTrue(result["possible"])
        self.assertEqual(result["target"], "DLYF")
        self.assertGreater(result["expected"]["success"], 0.9)


if __name__ == "__main__":
    unittest.main()
