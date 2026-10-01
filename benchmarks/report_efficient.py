"""Build a comparable cost/quality report from live runs and saved baselines."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import statistics
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from efficient import atomic_json, validate
from legacy_score import ground_truth_by_image, extract_prediction
from evaluation import _count_threshold_matches, _count_matches, soft_signature, aggregate_prf


def usage_cost(usage, pricing):
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
    return (prompt - cached) * float(pricing["prompt"]) + cached * float(pricing.get("input_cache_read", pricing["prompt"])) + completion * float(pricing["completion"])


def describe(runs, gt, pricing, catalog=None):
    tp = pred = expected = exact = molecules = invalid = flagged = 0
    prompt_tokens = completion_tokens = reasoning_tokens = 0
    cost = upstream_cost = 0
    upstream_cost_calls = unknown_usage_calls = 0
    latencies = []
    per_image = []
    for run in runs:
        name = run["image"]
        prediction = extract_prediction(run)
        truth = gt[name]
        matches = _count_threshold_matches(prediction, truth, 0.5, False)
        exact_matches = _count_matches([soft_signature(r) for r in prediction], [soft_signature(r) for r in truth])
        check = validate({"reactions": prediction})
        tp += matches
        exact += exact_matches
        pred += len(prediction)
        expected += len(truth)
        molecules += check["molecule_count"]
        invalid += len(check["invalid_smiles"])
        flagged += bool(check["needs_review"])
        latencies.append(run.get("wall_seconds", 0))
        meta = run.get("result", {}).get("meta", run.get("meta", {}))
        usages = [(meta.get("usage", {}), pricing)]
        if "review" in meta:
            review_model = meta["review"].get("model", "gpt-5.6-sol")
            review_id = "openai/" + review_model if review_model.startswith("gpt-") else review_model
            review_price = catalog.get(review_id, {}).get("pricing", pricing) if catalog else pricing
            usages = [(meta.get("source_usage", {}), pricing), (meta["review"].get("usage", {}), review_price)]
        usages += [(old.get("result", {}).get("meta", old.get("meta", {})).get("usage", {}), pricing)
                   for old in run.get("previous_attempts", []) if old.get("error") != "not_attempted"]
        for usage, call_price in usages:
            prompt_tokens += usage.get("prompt_tokens", 0)
            completion_tokens += usage.get("completion_tokens", 0)
            reasoning_tokens += usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
            if call_price:
                cost += usage_cost(usage, call_price)
            if usage.get("cost") is not None:
                upstream_cost += float(usage["cost"])
                upstream_cost_calls += 1
            if not usage and run.get("error") != "not_attempted":
                unknown_usage_calls += 1
        per_image.append({"image": name, "ok": run["exit_code"] == 0,
                          "tp": matches, "exact_tp": exact_matches,
                          "n_pred": len(prediction), "n_gt": len(truth),
                          "needs_review": check["needs_review"], "invalid_smiles": len(check["invalid_smiles"]),
                          "latency_seconds": latencies[-1]})
    n = len(runs)
    return {"images": n, "successful_images": sum(r["exit_code"] == 0 for r in runs),
            "soft_match": aggregate_prf(tp, pred, expected),
            "exact_match": aggregate_prf(exact, pred, expected),
            "mean_seconds": statistics.mean(latencies) if latencies else 0,
            "median_seconds": statistics.median(latencies) if latencies else 0,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "reasoning_tokens": reasoning_tokens, "estimated_usd": cost if pricing else None,
            "unknown_usage_calls": unknown_usage_calls,
            "provider_reported_usd": upstream_cost if upstream_cost_calls else None,
            "provider_cost_calls": upstream_cost_calls,
            "estimated_usd_per_image": cost / n if pricing and n else None,
            "estimated_usd_per_match": cost / tp if pricing and tp else None,
            "invalid_smiles": invalid, "molecules": molecules, "flagged_images": flagged,
            "per_image": per_image}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--baseline-dir", type=Path, required=True)
    p.add_argument("--gt", type=Path, required=True)
    p.add_argument("--catalog", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    gt = ground_truth_by_image(args.gt)
    catalog = json.loads(args.catalog.read_text())
    summaries = {}
    manifests = []
    for path in sorted(args.run_dir.glob("*/aggregate.json")):
        data = json.loads(path.read_text())
        name = data["backend"]
        priced_model = data["config"]["model"]
        catalog_name = "google/" + priced_model if priced_model.startswith("gemini-") else priced_model
        summaries[name] = describe(data["runs"], gt, catalog.get(catalog_name, {}).get("pricing"), catalog)
        manifests.append(set(data["images"]))
    selected = set.intersection(*manifests) if manifests else set()
    medium = json.loads((args.baseline_dir / "sol_vision_local_full_prompt_v4_medium_2026-09-21/aggregate.json").read_text())
    review = json.loads((args.baseline_dir / "sol_high_review_probe_2026-09-21/aggregate.json").read_text())
    source = {r["image"]: r for r in medium["runs"]}
    for run in review["runs"]:
        original = source[run["image"]]
        run["wall_seconds"] += original["wall_seconds"]
        run["result"]["meta"]["source_usage"] = original["result"]["meta"]["usage"]
    pricing = catalog["openai/gpt-5.6-sol"]["pricing"]
    for name, data in [("saved_sol_medium", medium), ("saved_sol_medium_high_review", review)]:
        summaries[name] = describe([r for r in data["runs"] if r["image"] in selected], gt, pricing)
        summaries[name]["historical"] = True
        summaries[name]["date"] = "2026-09-21"
    output = {"models": summaries, "pricing_basis": "2026-10-01 OpenRouter catalog reference rates; HKUST actual charges can differ. Completion totals include reported reasoning tokens; failures/retries with usage are included.",
              "baseline_note": "Saved predictions rescored on identical images with current RDKit. Baseline review latency and cost include both extraction and review.",
              "scope": "R-group reactants and products only. Conditions not scored. Soft match strips stereochemistry and salts with threshold 0.5; exact match also strips stereochemistry and salts.",
              "account_measurement": json.loads((args.run_dir / "summary.json").read_text()) if (args.run_dir / "summary.json").exists() else None}
    atomic_json(args.output, output)
    for name, s in summaries.items():
        print(name, f"{s['successful_images']}/{s['images']}", f"F1 {s['soft_match']['f1']:.3f}",
              f"exact {s['exact_match']['f1']:.3f}", f"{s['mean_seconds']:.1f}s", f"USD {s['estimated_usd']}")


if __name__ == "__main__":
    main()
