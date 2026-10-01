"""Score ChemEAGLE benchmark aggregates against GT4 detailed reactions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation import _count_threshold_matches, aggregate_prf, align_reactions


def normalize_reaction(value: dict) -> dict:
    return {
        "reactants": [{"smiles": item} for item in value.get("reactants", [])],
        "products": [{"smiles": item} for item in value.get("products", [])],
        "conditions": [],
    }


def ground_truth_by_image(path: Path) -> dict[str, list[dict]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    output: dict[str, list[dict]] = {}
    for row in rows:
        name = row["file_name"].replace(
            "10.1002:anie.202313578", "10.1002_anie.202313578"
        )
        details = row.get("detailed_reactions", {})
        output[name] = [normalize_reaction(value) for value in details.values()]
    return output


def extract_prediction(run: dict) -> list[dict]:
    result = run.get("result", {}).get("results", [])
    if not result or not isinstance(result[0], dict):
        return []
    reactions = result[0].get("reactions", [])
    return [item for item in reactions if isinstance(item, dict)]


def score(
    path: Path, ground_truth: dict[str, list[dict]], *, include_ged: bool = True
) -> dict:
    aggregate = json.loads(path.read_text(encoding="utf-8"))
    total_tp = total_pred = total_gt = 0
    total_ged = 0.0
    total_slots = 0
    elapsed: list[float] = []
    per_image: list[dict] = []

    for run in aggregate.get("runs", []):
        image = run["image"]
        predicted = extract_prediction(run)
        expected = ground_truth.get(image, [])
        tp = _count_threshold_matches(
            predicted, expected, threshold=0.5, use_conditions=False
        )
        metrics = aggregate_prf(tp, len(predicted), len(expected))
        alignment = align_reactions(predicted, expected) if include_ged else []
        ged_sum = sum(cost for _, _, cost in alignment) if include_ged else 0.0
        slots = max(len(predicted), len(expected), 1)
        wall = float(run.get("wall_seconds", 0.0))
        elapsed.append(wall)
        total_tp += tp
        total_pred += len(predicted)
        total_gt += len(expected)
        total_ged += ged_sum
        total_slots += slots
        per_image.append(
            {
                "image": image,
                "ok": run.get("exit_code") == 0,
                "wall_seconds": wall,
                "n_pred": len(predicted),
                "n_gt": len(expected),
                "soft_tp": tp,
                "soft_precision": metrics["precision"],
                "soft_recall": metrics["recall"],
                "soft_f1": metrics["f1"],
                "ged_per_reaction": ged_sum / slots if include_ged else None,
            }
        )

    summary = aggregate_prf(total_tp, total_pred, total_gt)
    return {
        "backend": aggregate.get("backend"),
        "status": aggregate.get("status"),
        "completed_images": len(per_image),
        "successful_images": sum(1 for item in per_image if item["ok"]),
        "total_seconds": sum(elapsed),
        "mean_seconds": sum(elapsed) / len(elapsed) if elapsed else None,
        "soft_match": summary,
        "ged_avg_per_reaction": (
            total_ged / total_slots if include_ged and total_slots else None
        ),
        "per_image": per_image,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--normal", type=Path, required=True)
    parser.add_argument("--azure", type=Path, required=True)
    parser.add_argument("--gt", type=Path, required=True)
    parser.add_argument("--skip-ged", action="store_true")
    args = parser.parse_args()
    gt = ground_truth_by_image(args.gt)
    print(
        json.dumps(
            {
                "normal": score(args.normal, gt, include_ged=not args.skip_ged),
                "azure": score(args.azure, gt, include_ged=not args.skip_ged),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
