import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from PIL import Image
from efficient import Config, ExtractionError, extract, parse_result, validate

VALID = {"reactions": [{"reaction_id": "1", "reactants": [{"smiles": "CCO"}],
                       "products": [{"smiles": "CC=O"}], "conditions": []}]}


class EfficiencyTests(unittest.TestCase):
    def response(self, result=VALID, finish="stop"):
        r = Mock(ok=True)
        r.json.return_value = {"model": "test", "choices": [{"finish_reason": finish,
                               "message": {"content": json.dumps(result)}}],
                               "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
        return r

    def test_cache_avoids_paid_call_but_changes_in_model_invalidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "image.png"
            Image.new("RGB", (10, 10), "white").save(image)
            with patch("efficient.requests.post", return_value=self.response()) as post:
                extract(image, "test", cache_dir=root / "cache")
                _, meta = extract(image, "test", cache_dir=root / "cache")
                self.assertEqual(post.call_count, 1)
                self.assertEqual(meta["request_count"], 0)
                self.assertEqual(meta["usage"], {})
                extract(image, "test", Config(model="other"), cache_dir=root / "cache")
                self.assertEqual(post.call_count, 2)

    def test_truncated_answer_is_not_cached_and_usage_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "image.png"
            Image.new("RGB", (10, 10)).save(image)
            with patch("efficient.requests.post", return_value=self.response(finish="length")) as post:
                with self.assertRaises(ExtractionError) as caught:
                    extract(image, "test", cache_dir=root / "cache")
                self.assertEqual(post.call_count, 1)
                self.assertEqual(caught.exception.metadata["usage"]["completion_tokens"], 50)
                self.assertFalse((root / "cache").exists())

    def test_invalid_smiles_remain_visible_and_require_review(self):
        result = json.loads(json.dumps(VALID))
        result["reactions"][0]["products"][0]["smiles"] = "C1CCCC"
        validated = validate(parse_result(json.dumps(result)))
        self.assertTrue(validated["needs_review"])
        self.assertEqual(len(validated["invalid_smiles"]), 1)
        self.assertEqual(result["reactions"][0]["products"][0]["smiles"], "C1CCCC")

    def test_empty_and_duplicate_results_require_review(self):
        self.assertTrue(validate({"reactions": []})["needs_review"])
        self.assertTrue(validate({"reactions": VALID["reactions"] * 2})["needs_review"])

    def test_wildcard_placeholders_cannot_pass_clean_cache_gate(self):
        result = json.loads(json.dumps(VALID))
        result["reactions"][0]["products"][0]["smiles"] = "*CC"
        self.assertTrue(validate(result)["needs_review"])
        self.assertEqual(len(validate(result)["unresolved_smiles"]), 1)

    def test_malformed_rows_cannot_be_silently_dropped(self):
        with self.assertRaises(ExtractionError):
            parse_result('{"reactions": [null]}')
        with self.assertRaises(ExtractionError):
            parse_result('{"reactions": [{"reactants": [], "products": []}]}')


if __name__ == "__main__":
    unittest.main()
