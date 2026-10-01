"""Optional visual review only when local validation flags an extraction."""
import base64
from io import BytesIO
from pathlib import Path
import time

from PIL import Image
import requests
from efficient import BASE_URL, ExtractionError, parse_result, validate

REVIEW_PROMPT = """Review the candidate reaction extraction against the figure and close-ups.
Preserve entries that agree with the drawing. Correct only image-supported errors
in atoms, bonds, ring connectivity, substitution positions or stereochemistry.
The crops overlap; they are not separate reactions. Preserve the number of scope
rows and each row's identity. Reactants are only structures drawn left of the
arrow; exclude catalysts and all species above/below arrows. Expand R groups.
Use complete valid SMILES. Return JSON only with reactions, reaction_id,
reactants:[{smiles:...}], products:[{smiles:...}], conditions:[] for each row.
"""


def refine(image_path: Path, draft: dict, api_key: str, *, model="gpt-5.6-sol", timeout=300):
    import json
    before = validate(draft)
    if not before["needs_review"]:
        return draft, {"requested": False, "accepted": False, "usage": {}, "wall_seconds": 0, "request_count": 0}
    content = [{"type": "text", "text": "Candidate JSON:\n" + json.dumps(draft)}]
    content.append({"type": "text", "text": "Local validation flags:\n" + json.dumps(before)})
    with Image.open(image_path) as src:
        image = src.convert("RGB")
        w, h = image.size
        regions = [("Full figure", image), ("Top close-up", image.crop((0, 0, w, max(1, int(h*.45))))),
                   ("Middle close-up", image.crop((0, int(h*.25), w, max(1, int(h*.78))))),
                   ("Bottom close-up", image.crop((0, int(h*.55), w, h)))]
        for label, region in regions:
            region.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            region.save(buffer, format="PNG")
            content.extend([{"type": "text", "text": label}, {"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode(), "detail": "high"}}])
    payload = {"model": model, "reasoning_effort": "high", "max_completion_tokens": 30000,
               "response_format": {"type": "json_object"}, "messages": [
                   {"role": "system", "content": REVIEW_PROMPT}, {"role": "user", "content": content}]}
    started = time.monotonic()
    meta = {"requested": True, "accepted": False, "model": model, "usage": {}, "request_count": 1}
    try:
        response = requests.post(BASE_URL + "/chat/completions", json=payload,
                                 headers={"api-key": api_key}, timeout=timeout)
        if not response.ok:
            raise ExtractionError(f"http_{response.status_code}")
        body = response.json()
        meta["usage"] = body.get("usage", {})
        choice = body["choices"][0]
        meta["finish_reason"] = choice.get("finish_reason")
        if choice.get("finish_reason") in ("length", "content_filter"):
            raise ExtractionError("truncated_or_filtered")
        meta["response_text"] = choice["message"].get("content")
        reviewed = parse_result(meta["response_text"])
        after = validate(reviewed)
        meta["validation"] = after
        if len(reviewed["reactions"]) != len(draft["reactions"]):
            raise ExtractionError("row_count_changed")
        original_ids = [str(row.get("reaction_id", "")) for row in draft["reactions"]]
        reviewed_ids = [str(row.get("reaction_id", "")) for row in reviewed["reactions"]]
        if all(original_ids) and sorted(original_ids) != sorted(reviewed_ids):
            raise ExtractionError("row_identity_changed")
        if len(after["invalid_smiles"]) > len(before["invalid_smiles"]) or len(after["unresolved_smiles"]) > len(before["unresolved_smiles"]):
            raise ExtractionError("validation_regression")
        if len(after["duplicate_rows"]) > len(before["duplicate_rows"]):
            raise ExtractionError("duplicate_regression")
        meta["accepted"] = True
        return reviewed, meta
    except Exception as e:
        meta["error"] = str(e) if isinstance(e, ExtractionError) else type(e).__name__
        return draft, meta
    finally:
        meta["wall_seconds"] = time.monotonic() - started
