"""Assemble the durable experiment report from scored artifacts."""
import csv
import json
from pathlib import Path
import shutil


def main():
    root = Path(__file__).resolve().parents[1]
    reports = root / "reports"
    def load(name):
        return json.loads((reports / (name + ".json")).read_text())
    full = load("full-economical")["models"]
    normal = load("full-gemini-default")["models"]
    selective = load("selective-review")["models"]
    kimi = load("full-kimi-no-reasoning")["models"]
    rows = [
        ("Saved Sol medium + high review", selective["saved_sol_medium_high_review"]),
        ("Lite: Gemini Flash + selective Sol review", selective["gemini-3.7-flash-selective-sol-review"]),
        ("Gemini 3.7 Flash, default reasoning", normal["gemini-3.7-flash"]),
        ("Gemini 3.7 Flash, low reasoning", full["gemini-3.7-flash"]),
        ("Kimi K3, reasoning off", kimi["moonshotai/kimi-k3"]),
        ("Qwen 3.8 Flash service, reasoning off", full["qwen/qwen3.8-flash"]),
        ("MiniMax M3, reasoning off", full["minimax/minimax-m3"]),
    ]
    with (reports / "comparison.csv").open("w") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["profile", "successful_images", "images", "soft_f1", "exact_f1", "mean_seconds", "reference_usd", "invalid_smiles"])
        for name, s in rows:
            writer.writerow([name, s["successful_images"], s["images"], s["soft_match"]["f1"], s["exact_match"]["f1"], s["mean_seconds"], s["estimated_usd"], s["invalid_smiles"]])
    def table(entries):
        lines = ["| Configuration | Successful / images | Benchmark F1 | Exact F1 | Mean seconds/image | Reference USD |",
                 "|---|---:|---:|---:|---:|---:|"]
        for name, s in entries:
            lines.append(f"| {name} | {s['successful_images']}/{s['images']} | {s['soft_match']['f1']:.3f} | {s['exact_match']['f1']:.3f} | {s['mean_seconds']:.1f} | ${s['estimated_usd']:.3f} |")
        return "\n".join(lines)
    best = rows[1][1]
    baseline = rows[0][1]
    reduction = 100 * (1 - best["estimated_usd"] / baseline["estimated_usd"])
    speedup = baseline["mean_seconds"] / best["mean_seconds"]
    balance = load("account_balance")
    probes = load("probe")["models"]
    default_probes = load("gemini-default-probe")["models"]
    larger_pro = load("gemini-pro-32k-probe")["models"]
    probe_rows = [("Gemini Pro 3.1, low reasoning, 16k cap", probes["gemini-3.1-pro-preview"]),
                  ("Gemini Pro 3.1, default reasoning, 16k cap", default_probes["gemini-3.1-pro-preview"]),
                  ("Gemini Pro 3.1, default reasoning, 32k cap", larger_pro["gemini-3.1-pro-preview"]),
                  ("Kimi K3, low reasoning, 16k cap", load("kimi-low-probe")["models"]["moonshotai/kimi-k3"])]
    text = f"""# ChemEAGLE cost optimization — 1 October 2026

The recommended variant is Gemini 3.7 Flash with normal reasoning, followed by
Sol high visual review only when local validation flags an image. On the current
73-image GT4 benchmark it reached **F1 {best['soft_match']['f1']:.3f} and exact F1
{best['exact_match']['f1']:.3f}**, versus the saved two-pass baseline's
{baseline['soft_match']['f1']:.3f} and {baseline['exact_match']['f1']:.3f}.
Its reference token cost was **{reduction:.1f}% lower**, and average per-image
latency was **{speedup:.2f} times lower**. These are measurements from one run;
the small accuracy difference does not establish statistical superiority.

## Full benchmark

{table(rows)}

All seven configurations above cover the same 73 available images and 893
ground-truth reactions. Every image was attempted in the live full runs. Failed
responses contribute zero predictions while keeping their ground truth in the
recall denominator. Qwen had one final failed response; MiniMax had three.
Successful results were reused when extending probes into full runs. Token
costs include retained billed retries with reported usage.

## Why this saves cost

The baseline calls Sol twice for every figure, including a full image and three
overlapping crops for the review. Lite uses one Flash call per figure and local
RDKit checks for invalid SMILES, unresolved wildcard atoms, empty results and
duplicate reactions. Only **5 of 73 images** triggered the expensive visual
review: **78 total model calls**, versus 146 baseline calls. No ground truth,
expected row counts or expected molecules were sent to either model.

All five reviews preserved row count and row identities, and none increased
invalid SMILES, unresolved placeholders or duplicates. The reviews corrected
all 68 invalid source SMILES; the final result had **0 invalid SMILES among
2,543 molecular entries**. One image retains a duplicate-row review flag.
Valid SMILES alone do not prove that a graph agrees with its drawing.

Clean results can be cached by image, prompt, model, reasoning, resolution and
review policy. The live cache smoke test returned the same result with one paid
request on the first invocation and zero requests on the second. Lite runs on
CPU without specialist checkpoints or PyTorch/CUDA.

## Other settings tested

{table(probe_rows)}

These rows use the same separate 12-image probe, covering scopes with 3–33
reactions, and its 156 ground-truth reactions. Gemini Pro's 16k budget was often
consumed by reasoning, producing truncated or invalid JSON. Raising its budget
to 32k improved completion reliability but remained expensive and weaker on
this task. Unknown usage from earlier timeouts makes those prices lower bounds.
MiniMax's default-reasoning experiment completed only one of eight attempts;
seven timed out and four other probe inputs were left unattempted after the
account-wide spend checkpoint. It is excluded from the quality ranking.

[MiniMax M3](https://huggingface.co/MiniMaxAI/MiniMax-M3) and
[Kimi K3](https://huggingface.co/moonshotai/Kimi-K3) are the open-weight candidates.
Their tested direct image-to-SMILES routes lost substantial accuracy. The Qwen
Flash service was also tested; its weight availability was not verified. A
future experiment could combine open models with specialist structure
recognition rather than asking them to reconstruct every SMILES directly.

## Cost and measurement limits

USD figures use the saved 1 October [OpenRouter model catalog](https://openrouter.ai/api/v1/models)
as common reference pricing, including reported reasoning tokens and cache
discounts. They are estimates, and HKUST's actual routing rates can differ.
Provider-reported costs, token details and unknown-usage counts are retained in
the JSON score reports. The observed HKUST account balance fell from
HK${balance['before_hkd']:.2f} to HK${balance['after_hkd']:.2f}, a
**HK${balance['observed_delta_hkd']:.2f} account-wide delta** across all probes,
retries, full runs and the cache smoke test. Concurrent outside account activity
and late provider billing can affect that observation. No credits were purchased.

The baseline consists of saved 21 September predictions, rescored today using
the same evaluator and current RDKit. Its latency includes both extraction and
review; its cost re-prices both stages at the common reference rates. Live runs
used bounded concurrency, so latency is an observed request measurement under
that workload rather than a controlled infrastructure comparison.

GT4 contains 78 rows but only 73 corresponding PNGs are available locally.
Only the existing colon-to-underscore filename mismatch was normalized. The
new images were bounded to 1,800 pixels on the longest side. Soft F1 uses the
existing 0.5 reactant/product overlap rule. Exact F1 requires complete matching
reactant/product multisets. Both canonicalize SMILES, strip stereochemistry and
keep the largest salt fragment. Conditions and PDF extraction are outside this
experiment. These results do not establish performance on other datasets.

The upgraded local ChemEagle checkout already defaults to `gemini-3.7-flash`,
which informed that candidate. Yufan's email has **not been verified**: the HKUST
mailbox requires user sign-in in the in-app browser. No email was sent.

## Use the branch

Branch: `mathus/chemeagle-cost-optimized`. The original dirty checkout was
preserved; this work is isolated in `ChemEagle-efficient`.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.efficient.txt
# Set HKUST_API_KEY privately.
.venv/bin/python efficient.py figure.png --output result.json --cache .cache --review
```

Omit `--review` for the measured single-pass mode. Reduced reasoning is available
with `--reasoning economical`, with the quality tradeoff shown above. Failed,
truncated or locally flagged results are not cached. The original multi-agent
pipeline is retained. Ten focused tests passed, and all five accepted live
reviews passed the final deterministic gates.

The score JSONs, `comparison.csv`, runtime versions, dataset manifest and
per-image prediction artifacts accompany this report. `benchmarks/run_efficient.py`
repeats the API runs; `benchmarks/report_efficient.py` repeats the scoring;
`benchmarks/review_flagged.py` repeats selective review.
"""
    (reports / "cost_optimization_2026-10-01.md").write_text(text)
    predictions = reports / "predictions"
    predictions.mkdir(exist_ok=True)
    sources = {"gemini_flash_default": "full-gemini-default/gemini-3.7-flash",
               "gemini_flash_selective_review": "selective-review/gemini-selective",
               "gemini_flash_low": "full-economical/gemini-3.7-flash",
               "minimax_m3_off": "full-economical/minimax__minimax-m3",
               "qwen_flash_off": "full-economical/qwen__qwen3.8-flash",
               "kimi_k3_off": "full-kimi-no-reasoning/moonshotai__kimi-k3"}
    for name, directory in sources.items():
        data = json.loads((root / "benchmark-runs" / directory / "aggregate.json").read_text())
        def compact(value):
            if isinstance(value, dict):
                return {k: compact(v) for k,v in value.items() if k != "response_text"}
            if isinstance(value, list):
                return [compact(v) for v in value]
            return value
        runs = data.pop("runs")
        # Keep valid aggregate JSON, with one image record per line. Raw answer
        # text remains in benchmark-runs; parsed predictions and usage stay here.
        header = json.dumps(compact(data), ensure_ascii=False, separators=(",", ":"))[:-1]
        body = ",\n".join(json.dumps(compact(r), ensure_ascii=False, separators=(",", ":")) for r in runs)
        (predictions / (name + ".json")).write_text(header + ',"runs":[\n' + body + '\n]}\n')
    shutil.copyfile(root / "benchmark-runs/full-gemini-default/manifest.json", reports / "dataset_manifest.json")
    shutil.copyfile(root / "benchmark-runs/full-gemini-default/models.json", reports / "hkust_model_catalog_2026-10-01.json")
    for name in ["probe_live", "full-gemini-default-live", "selective-review-live", "kimi-low-probe-incomplete"]:
        (reports / (name + ".json")).unlink(missing_ok=True)
    print("Report and prediction artifacts saved")


if __name__ == "__main__":
    main()
