import json
from pathlib import Path
import tempfile
import unittest
from benchmarks.legacy_score import score


REACTION = {"reactants": [{"smiles": "CCO"}], "products": [{"smiles": "CC=O"}]}


class BenchmarkScoringTests(unittest.TestCase):
    def test_failed_image_stays_in_recall_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aggregate.json"
            path.write_text(json.dumps({"runs": [
                {"image": "good.png", "exit_code": 0, "result": {"results": [{"reactions": [REACTION]}]}},
                {"image": "failed.png", "exit_code": 1, "error": "transport_error"}]}))
            result = score(path, {"good.png": [REACTION], "failed.png": [REACTION]}, include_ged=False)
            self.assertEqual(result["successful_images"], 1)
            self.assertEqual(result["soft_match"]["n_gt"], 2)
            self.assertEqual(result["soft_match"]["recall"], 0.5)


if __name__ == "__main__":
    unittest.main()
