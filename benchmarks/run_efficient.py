"""Resumable, bounded HKUST benchmark; ground truth is used only for scoring."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
import requests
from efficient import BASE_URL, Config, ExtractionError, PROMPT, atomic_json, extract
from legacy_score import ground_truth_by_image, score


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--env-file", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--models", nargs="+", required=True)
    p.add_argument("--manifest", type=Path)
    p.add_argument("--seed-dir", type=Path, help="Reuse successful identical-config image predictions from an earlier probe")
    p.add_argument("--limit", type=int)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--max-tokens", type=int, default=16384)
    p.add_argument("--max-image-side", type=int, default=1800)
    p.add_argument("--reasoning")
    p.add_argument("--max-spend-hkd", type=float, default=40)
    args = p.parse_args()
    if len(set(args.models)) != len(args.models) or args.workers < 1 or args.max_spend_hkd <= 0 or args.max_tokens < 1:
        raise SystemExit("Models must be unique; workers, token budget, and spend checkpoint must be positive")
    env = dotenv_values(args.env_file)
    key = env.get("NEW_API_KEY") or env.get("API_KEY")
    if not key:
        raise SystemExit("No HKUST key configured")
    headers = {"api-key": key}
    def balance():
        response = requests.get(BASE_URL + "/balance", headers=headers, timeout=30)
        response.raise_for_status()
        return float(response.json()["credit"])
    start_credit = balance()
    available = sorted(x.name for x in args.input_dir.glob("*.png"))
    images = json.loads(args.manifest.read_text()) if args.manifest else available
    if args.limit:
        images = images[:args.limit]
    if any(name not in available for name in images) or len(set(images)) != len(images):
        raise SystemExit("Manifest contains missing or duplicate images")
    gt = ground_truth_by_image(args.input_dir / "GT4.json")
    if any(name not in gt for name in images):
        raise SystemExit("Image without ground truth")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    catalog = requests.get(BASE_URL + "/models", headers=headers, timeout=30)
    catalog.raise_for_status()
    atomic_json(args.output_dir / "models.json", catalog.json())
    atomic_json(args.output_dir / "manifest.json", {"images": images,
        "missing_images": sorted(set(gt) - set(available)),
        "ground_truth_sha256": hashlib.sha256((args.input_dir / "GT4.json").read_bytes()).hexdigest(),
        "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "image_sha256": {name: hashlib.sha256((args.input_dir / name).read_bytes()).hexdigest() for name in images},
        "baseline_scoring": "Canonical SMILES, stereochemistry stripped, largest salt fragment, threshold 0.5, no conditions"})
    configs = {name: Config(model=name, max_tokens=args.max_tokens,
                           max_image_side=args.max_image_side, reasoning=args.reasoning) for name in args.models}
    aggregates = {}
    paths = {}
    for name, config in configs.items():
        path = args.output_dir / name.replace("/", "__") / "aggregate.json"
        paths[name] = path
        if path.exists():
            data = json.loads(path.read_text())
            if data["config"] != asdict(config) or data["images"] != images or data["prompt_sha256"] != hashlib.sha256(PROMPT.encode()).hexdigest():
                raise SystemExit("Resume configuration mismatch; use another output directory")
        else:
            data = {"backend": name, "status": "pending", "runs": [],
                    "config": asdict(config), "images": images,
                    "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
                    "expected_images": len(images), "started_at": time.time()}
            seed_path = args.seed_dir / name.replace("/", "__") / "aggregate.json" if args.seed_dir else None
            if seed_path and seed_path.is_file():
                seed = json.loads(seed_path.read_text())
                if seed["config"] != asdict(config) or seed["prompt_sha256"] != data["prompt_sha256"]:
                    raise SystemExit("Seed configuration mismatch")
                data["runs"] = [r for r in seed["runs"] if r["exit_code"] == 0 and r["image"] in images
                    and r.get("result", {}).get("meta", {}).get("input_sha256") == hashlib.sha256((args.input_dir / r["image"]).read_bytes()).hexdigest()]
                data["seeded_images"] = len(data["runs"])
                data["seed_source"] = str(seed_path)
        aggregates[name] = data
    def one(item):
        name, image = item
        started = time.monotonic()
        run = {"image": image, "exit_code": 1}
        try:
            result, meta = extract(args.input_dir / image, key, configs[name])
            run.update(exit_code=0, result={"results": [result], "meta": meta})
        except ExtractionError as e:
            run.update(error=str(e), meta=e.metadata)
        except Exception as e:
            run.update(error=type(e).__name__)
        run["wall_seconds"] = time.monotonic() - started
        return name, run
    stopped = set()
    started = time.monotonic()
    # Bounded batches avoid queuing a whole paid corpus before credit checks.
    todo = [(name, image) for image in images for name in args.models
            if not any(r["image"] == image and r["exit_code"] == 0 for r in aggregates[name]["runs"])]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for offset in range(0, len(todo), args.workers):
            current_credit = balance()
            if start_credit - current_credit >= args.max_spend_hkd:
                print("spend_limit_reached", flush=True)
                break
            batch = [item for item in todo[offset:offset + args.workers] if item[0] not in stopped]
            futures = [pool.submit(one, item) for item in batch]
            for future in as_completed(futures):
                name, run = future.result()
                data = aggregates[name]
                previous = next((r for r in data["runs"] if r["image"] == run["image"]), None)
                if previous:
                    old_attempts = previous.get("previous_attempts", [])
                    run["previous_attempts"] = old_attempts + ([{k:v for k,v in previous.items() if k != "previous_attempts"}] if previous.get("error") != "not_attempted" else [])
                data["runs"] = [r for r in data["runs"] if r["image"] != run["image"]] + [run]
                data["runs"].sort(key=lambda r: images.index(r["image"]))
                data["status"] = "running"
                atomic_json(paths[name], data)
                attempted = sum(r.get("error") != "not_attempted" for r in data["runs"])
                print(f"{name} attempted {attempted}/{len(images)} {run['error'] if run['exit_code'] else 'ok'} {run['wall_seconds']:.1f}s", flush=True)
                if run.get("error") in {"image_input_unsupported", "http_400", "http_401", "http_403", "http_404", "insufficient_credit"}:
                    stopped.add(name)
                if run.get("error") == "insufficient_credit":
                    stopped.update(args.models)
    end_credit = balance()
    summary = {}
    for name, data in aggregates.items():
        seen = {r["image"] for r in data["runs"]}
        # Score all intended images; failures and unattempted inputs count as misses.
        data["runs"] += [{"image": image, "exit_code": 1, "error": "not_attempted", "wall_seconds": 0} for image in images if image not in seen]
        data["status"] = "completed" if all(r["exit_code"] == 0 for r in data["runs"]) else "incomplete"
        atomic_json(paths[name], data)
        scored = score(paths[name], gt, include_ged=False)
        atomic_json(paths[name].parent / "score.json", scored)
        summary[name] = {k: v for k, v in scored.items() if k != "per_image"}
    atomic_json(args.output_dir / "summary.json", {"scores": summary,
        "balance_before_hkd": start_credit, "balance_after_hkd": end_credit,
        "balance_delta_hkd": start_credit - end_credit,
        "elapsed_seconds": time.monotonic() - started,
        "cost_note": "Account balance delta; includes concurrent account activity if any. Model attribution requires usage pricing."})


if __name__ == "__main__":
    main()
