import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from PIL import Image
from efficient_review import refine

DRAFT = {"reactions": [{"reaction_id": "1", "reactants": [{"smiles": "CCO"}], "products": [{"smiles": "C1CCCC"}]}]}


class ReviewTests(unittest.TestCase):
    def run_review(self, result):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.png"
            Image.new("RGB", (100, 100)).save(path)
            response = Mock(ok=True)
            response.json.return_value = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}], "usage": {"completion_tokens": 30}}
            with patch("efficient_review.requests.post", return_value=response):
                return refine(path, DRAFT, "test")

    def test_accepts_image_review_when_row_identity_and_validation_are_preserved(self):
        fixed = json.loads(json.dumps(DRAFT))
        fixed["reactions"][0]["products"][0]["smiles"] = "CC=O"
        result, meta = self.run_review(fixed)
        self.assertTrue(meta["accepted"])
        self.assertEqual(result["reactions"][0]["products"][0]["smiles"], "CC=O")

    def test_row_drop_falls_back_and_retains_paid_usage(self):
        result, meta = self.run_review({"reactions": []})
        self.assertEqual(result, DRAFT)
        self.assertFalse(meta["accepted"])
        self.assertEqual(meta["error"], "row_count_changed")
        self.assertEqual(meta["usage"]["completion_tokens"], 30)

    def test_clean_result_does_not_make_another_model_call(self):
        fixed = json.loads(json.dumps(DRAFT))
        fixed["reactions"][0]["products"][0]["smiles"] = "CC=O"
        with patch("efficient_review.requests.post") as post:
            _, meta = refine(Path("unused.png"), fixed, "test")
            post.assert_not_called()
            self.assertEqual(meta["request_count"], 0)


if __name__ == "__main__":
    unittest.main()
