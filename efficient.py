"""ChemEAGLE Lite: one vision request, local validation, content-addressed cache.

This experimental extractor implements the GT4 reactant/product task. It does
not extract conditions or replace the full production ChemEAGLE pipeline.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image
from rdkit import Chem, RDLogger

RDLogger.DisableLog("rdApp.*")
BASE_URL = "https://hkust.azure-api.net/hkust-genai/v1"
PROMPT = """Extract the detailed chemical reactions shown in the image.
For each labeled product in the substrate scope, return one reaction. Read the
generic reaction at the top to reconstruct that row's starting materials.
Reactants means only molecular structures explicitly drawn on the left side
of the reaction arrow, including structures joined by a plus sign. Do not put
anything above or below an arrow into reactants. Transcribe exactly what is drawn:
count atoms and bonds, preserve substitution positions and stereochemistry.
Use complete valid SMILES. Expand all R groups and abbreviations; never put R,
Ar, Ph, Me, Et, X, names or locants inside a SMILES. Exclude catalysts, bases,
solvents, temperatures, times and yields. Include drawn rows with trace or 0%
yield. Omit a row if its complete molecular graph cannot be read.
Return JSON only: {"reactions":[{"reaction_id":"row label or index",
"reactants":[{"smiles":"..."}],"products":[{"smiles":"..."}],"conditions":[]}]}
Keep conditions empty. Check SMILES syntax and valence before answering.
"""


@dataclass(frozen=True)
class Config:
    model: str = "gemini-3.7-flash"
    max_tokens: int = 16384
    max_image_side: int = 1800
    reasoning: str | None = None
    timeout: int = 300
    base_url: str = BASE_URL

    def __post_init__(self):
        if self.max_tokens < 1 or self.max_image_side < 0 or self.timeout < 1:
            raise ValueError("Token budget and timeout must be positive; image bound must be nonnegative")


class ExtractionError(RuntimeError):
    def __init__(self, code: str, metadata: dict | None = None):
        super().__init__(code)
        self.metadata = metadata or {}


def atomic_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def image_context(path: Path, max_side: int) -> tuple[str, dict]:
    with Image.open(path) as src:
        original = src.size
        image = src.convert("RGB")
        if max_side:
            image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        data = buffer.getvalue()
        return "data:image/png;base64," + base64.b64encode(data).decode(), {
            "original_size": original, "sent_size": image.size, "image_bytes": len(data)
        }


def parse_result(content: str) -> dict:
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
    try:
        result = json.loads(content)
    except (ValueError, TypeError):
        raise ExtractionError("invalid_json") from None
    if not isinstance(result, dict) or not isinstance(result.get("reactions"), list):
        raise ExtractionError("invalid_schema")
    for row in result["reactions"]:
        if not isinstance(row, dict):
            raise ExtractionError("invalid_reaction")
        for side in ("reactants", "products"):
            if not isinstance(row.get(side), list) or not row[side]:
                raise ExtractionError("missing_reaction_side")
            for mol in row[side]:
                if not isinstance(mol, dict) or not isinstance(mol.get("smiles"), str) or not mol["smiles"].strip():
                    raise ExtractionError("invalid_molecule_schema")
        row["conditions"] = []
    return result


def validate(result: dict) -> dict:
    invalid = []
    unresolved = []
    count = 0
    seen = set()
    duplicate = []
    for index, row in enumerate(result["reactions"]):
        signature = []
        for side in ("reactants", "products"):
            canon = []
            for mol in row[side]:
                count += 1
                smi = mol["smiles"]
                parsed = Chem.MolFromSmiles(smi)
                if parsed is None:
                    invalid.append({"row": index, "side": side, "smiles": smi})
                else:
                    if any(atom.GetAtomicNum() == 0 for atom in parsed.GetAtoms()):
                        unresolved.append({"row": index, "side": side, "smiles": smi})
                    canon.append(Chem.MolToSmiles(parsed))
            signature.append(tuple(sorted(canon)))
        key = tuple(signature)
        if key in seen:
            duplicate.append(index)
        seen.add(key)
    return {"molecule_count": count, "invalid_smiles": invalid,
            "unresolved_smiles": unresolved,
            "duplicate_rows": duplicate, "empty": not result["reactions"],
            "needs_review": bool(invalid or unresolved or duplicate or not result["reactions"])}


def extract(image: Path, api_key: str, config: Config = Config(), *, cache_dir: Path | None = None, review: bool = False) -> tuple[dict, dict]:
    if not api_key:
        raise ExtractionError("missing_api_key")
    url, image_meta = image_context(image, config.max_image_side)
    identity = {"image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                "prompt": PROMPT, "config": config.__dict__, "parser_version": 3,
                "selective_review": review}
    if review:
        from efficient_review import REVIEW_PROMPT
        identity["review_prompt"] = REVIEW_PROMPT
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    cache_path = cache_dir / f"{digest}.json" if cache_dir else None
    if cache_path and cache_path.is_file():
        saved = json.loads(cache_path.read_text())
        cached_meta = {**saved["meta"], "cache_hit": True, "request_count": 0, "usage": {}, "wall_seconds": 0.0}
        if "review" in cached_meta:
            cached_meta["source_usage"] = {}
            cached_meta["review"] = {**cached_meta["review"], "requested": False, "usage": {}, "request_count": 0, "wall_seconds": 0}
        return saved["result"], cached_meta
    payload = {"model": config.model, "messages": [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": "Extract every labeled detailed reaction; visually verify every atom and bond."},
            {"type": "image_url", "image_url": {"url": url, "detail": "high"}}]}]}
    if config.model.startswith("gpt-"):
        payload["max_completion_tokens"] = config.max_tokens
        payload["response_format"] = {"type": "json_object"}
    else:
        payload["max_tokens"] = config.max_tokens
    if config.reasoning:
        effort = config.reasoning
        if effort == "economical":
            effort = "none" if config.model.startswith(("qwen/", "minimax/")) else "low"
        if "/" in config.model:
            payload["reasoning"] = {"enabled": False} if effort == "none" else {"effort": effort}
        else:
            payload["reasoning_effort"] = effort
    started = time.monotonic()
    try:
        response = requests.post(config.base_url + "/chat/completions", json=payload,
                                 headers={"api-key": api_key}, timeout=config.timeout)
    except requests.RequestException:
        raise ExtractionError("transport_error") from None
    elapsed = time.monotonic() - started
    if not response.ok:
        body = response.text.lower()
        code = "insufficient_credit" if "insufficient credit" in body else f"http_{response.status_code}"
        if "image" in body and any(term in body for term in ("not support", "unsupported", "does not", "not allowed")):
            code = "image_input_unsupported"
        # Never persist provider error bodies: they can contain credentials or image data.
        raise ExtractionError(code, {"wall_seconds": elapsed, "request_count": 1})
    try:
        body = response.json()
    except ValueError:
        raise ExtractionError("invalid_provider_json", {"wall_seconds": elapsed, "request_count": 1}) from None
    choice = body.get("choices", [{}])[0]
    meta = {"requested_model": config.model, "returned_model": body.get("model"),
            "finish_reason": choice.get("finish_reason"), "usage": body.get("usage", {}),
            "wall_seconds": elapsed, "request_count": 1, "cache_hit": False,
            "input_sha256": identity["image_sha256"], "config": config.__dict__, **image_meta}
    if choice.get("finish_reason") in ("length", "content_filter"):
        raise ExtractionError("truncated_or_filtered", meta)
    content = choice.get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ExtractionError("empty_response", meta)
    # Persist the answer for audit/debugging, never the provider reasoning field.
    meta["response_text"] = content
    try:
        result = parse_result(content)
    except ExtractionError as error:
        error.metadata = meta
        raise
    meta["validation"] = validate(result)
    if review and meta["validation"]["needs_review"]:
        from efficient_review import refine
        result, review_meta = refine(image, result, api_key)
        meta["source_usage"] = meta.pop("usage")
        meta["source_model"] = config.model
        meta["review"] = review_meta
        meta["request_count"] += review_meta["request_count"]
        meta["wall_seconds"] += review_meta["wall_seconds"]
        meta["validation"] = validate(result)
    # Preserve invalid molecules for honest scoring, but flag them for user review.
    if cache_path and not meta["validation"]["needs_review"]:
        atomic_json(cache_path, {"result": result, "meta": meta})
    return result, meta


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("image", type=Path)
    p.add_argument("--model", default=Config.model)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cache", type=Path)
    p.add_argument("--reasoning", help="Omit for the model default; economical selects reduced reasoning")
    p.add_argument("--review", action="store_true", help="Review only locally flagged outputs with Sol high reasoning")
    args = p.parse_args()
    result, meta = extract(args.image, os.environ.get("HKUST_API_KEY", ""), Config(model=args.model, reasoning=args.reasoning), cache_dir=args.cache, review=args.review)
    atomic_json(args.output, {"result": result, "meta": meta})


if __name__ == "__main__":
    main()
