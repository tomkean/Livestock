"""The hidden-copy inference: never contradicts a card, and uses family. Run: python -m unittest test_inference"""
import unittest
from types import SimpleNamespace

import inference


def animal(id, top, mother=None, father=None):
    return SimpleNamespace(id=id, name=f"a{id}", code=f"S-{id}", genes_top=top, genes_bottom=None,
                           mother_id=mother, father_id=father)


class Inference(unittest.TestCase):
    def test_respects_the_cards(self):
        post = inference.infer([animal(1, "GOBGO")], sweeps=400, burn=100)["posterior"][1]
        self.assertAlmostEqual(post[2]["BB"], 1.0)  # red means Bad/Bad
        self.assertEqual(post[1].get("GG", 0) + post[1].get("GO", 0) + post[1].get("GB", 0), 0)  # grey: no Good copy
        self.assertAlmostEqual(sum(post[0].values()), 1.0)

    def test_a_grey_lamb_reveals_a_green_parents_hidden_copy(self):
        # Ram shows green; ewe is red (Bad/Bad). A grey lamb must have got Ok from the ram, so he is Good/Ok.
        herd = [animal(1, "BBBBB"), animal(2, "GGGGG"), animal(3, "OOOOO", mother=1, father=2)]
        post = inference.infer(herd, sweeps=600, burn=200)["posterior"][2]
        for gene in post:
            self.assertGreater(gene.get("GO", 0), 0.99)

    def test_green_parents_with_all_green_lambs_lean_good_good(self):
        # Many green lambs from a red ewe: each one got Good from the ram, so Good/Good becomes likely.
        herd = [animal(1, "BBBBB"), animal(2, "GGGGG")] + [animal(10 + k, "GGGGG", mother=1, father=2) for k in range(6)]
        lone = inference.infer([animal(2, "GGGGG")], sweeps=600, burn=200)["posterior"][2][0].get("GG", 0)
        tested = inference.infer(herd, sweeps=600, burn=200)["posterior"][2][0].get("GG", 0)
        self.assertGreater(tested, 0.8)
        self.assertLess(lone, 0.2)


if __name__ == "__main__":
    unittest.main()
