# ChemEAGLE: cost and quality comparison

**Decision report | 1 October 2026 | HKUST API | 73 images / 893 ground-truth reactions**

## Recommendation

Use Gemini 3.7 Flash with default reasoning and selective GPT-5.6 Sol high review. The optimized variant preserves benchmark quality while substantially reducing estimated token cost and observed latency. The cheapest open-weight candidates were much less accurate when asked to convert chemistry images directly into SMILES.

## Comparison with current ChemEagle

The reference is the saved ChemEagle Sol medium extraction plus Sol high review run from 21 September. It is the strongest saved two-pass baseline evaluated here. It was rescored with the same current evaluator as the new runs; the original pipeline was not rerun live. A separate upgraded local checkout already defaults to Gemini 3.7 Flash, so these findings compare a specific recorded pipeline, not every ChemEagle configuration.

| Metric | Saved ChemEagle baseline | Cost-optimized ChemEagle | Change |
|---|---:|---:|---:|
| Benchmark F1 | 0.8150 | 0.8199 | +0.0048 |
| Exact F1 | 0.8038 | 0.8176 | +0.0138 |
| Successful images | 73/73 | 73/73 | Same |
| Mean seconds per image | 157.8 | 39.4 | 75.0% lower |
| Reference token cost per 73 images | USD 9.159 | USD 1.926 | 79.0% lower |
| Reference token cost per image | USD 0.1255 | USD 0.0264 | Same pricing basis |
| Model calls | 146 | 78 | 46.6% fewer |
| Invalid SMILES | 6 | 0 | Syntax validity improved |

The small F1 improvement is not proof of superiority: this is a single benchmark run, and the review policy was developed on a 12-image subset reused in the full corpus. Treat the result as evidence of comparable quality at lower cost. F1 is a precision/recall measure, not the percentage of completely correct images.

At the same measured usage and reference rates, 1,000 similar images would cost approximately USD 125.47 for the baseline versus USD 26.39 for the optimized variant, saving USD 99.08. This is a linear illustration, not an HKUST quote; image complexity, retries and review frequency can change it.

## Full benchmark

| Configuration | Successful / images | Benchmark F1 | Exact F1 | Mean seconds/image | Reference USD |
|---|---:|---:|---:|---:|---:|
| Saved Sol medium + high review | 73/73 | 0.815 | 0.804 | 157.8 | $9.159 |
| Lite: Gemini Flash + selective Sol review | 73/73 | 0.820 | 0.818 | 39.4 | $1.926 |
| Gemini 3.7 Flash, default reasoning | 73/73 | 0.795 | 0.766 | 32.4 | $1.466 |
| Gemini 3.7 Flash, low reasoning | 73/73 | 0.777 | 0.692 | 24.0 | $0.934 |
| Kimi K3, reasoning off | 73/73 | 0.265 | 0.229 | 27.2 | $0.888 |
| Qwen 3.8 Flash service, reasoning off | 72/73 | 0.169 | 0.132 | 19.3 | $0.074 |
| MiniMax M3, reasoning off | 70/73 | 0.113 | 0.055 | 49.5 | $0.130 |

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

| Configuration | Successful / images | Benchmark F1 | Exact F1 | Mean seconds/image | Reference USD |
|---|---:|---:|---:|---:|---:|
| Gemini Pro 3.1, low reasoning, 16k cap | 12/12 | 0.452 | 0.382 | 12.1 | $0.213 |
| Gemini Pro 3.1, default reasoning, 16k cap | 5/12 | 0.194 | 0.194 | 106.2 | $3.114 |
| Gemini Pro 3.1, default reasoning, 32k cap | 11/12 | 0.456 | 0.456 | 145.6 | $2.890 |
| Kimi K3, low reasoning, 16k cap | 8/12 | 0.302 | 0.302 | 186.4 | $0.448 |

These rows use the same separate 12-image probe, covering scopes with 3-33
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
HK$277.84 to HK$168.92, a
**HK$108.92 account-wide delta** across all probes,
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

## Implementation and reproduction

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



## API provenance and model availability

All live inference requests in this experiment used the HKUST API, at `https://hkust.azure-api.net/hkust-genai/v1/chat/completions`. OpenRouter was used only as a public reference pricing catalog; the experiment did not send inference requests directly to OpenRouter.

The Sol baseline and selective reviewer use `gpt-5.6-sol`. The HKUST model catalog checked on 1 October did not list GPT-6 Sol or GPT-6.1 Sol. They were not benchmarked, and selecting either in Codex or signing into ChatGPT does not demonstrate access through HKUST. No conclusion about their chemistry quality or cost follows from this study.

## Deployment decision

Keep the optimized variant opt-in while validating it on an independent held-out dataset, particularly stereochemistry and salts. Use the Gemini default-reasoning single pass only when its modest quality reduction is acceptable. Do not replace the baseline with the tested Kimi, Qwen or MiniMax direct-conversion configurations on the basis of their low price alone.

The original pipeline remains available on this branch. Clean extraction results can be cached; live smoke verification showed zero API calls on the second identical request. Failed, truncated or flagged results do not enter the clean cache. The branch is `mathus/chemeagle-cost-optimized` in [Tew12345678910/ChemEagle](https://github.com/Tew12345678910/ChemEagle/tree/mathus/chemeagle-cost-optimized).

## Evidence files

- `reports/comparison.csv`: full-corpus comparison, including invalid SMILES counts.
- `reports/selective-review.json`: optimized profile scores and usage.
- `reports/predictions/`: per-image predictions for independent inspection.
- `reports/dataset_manifest.json`: benchmark image inventory and hashes.
- `reports/hkust_model_catalog_2026-10-01.json`: available HKUST models.
- `reports/openrouter_catalog_2026-10-01.json`: common pricing snapshot.
- `reports/account_balance.json` and `reports/cache_smoke.json`: account observation and live cache check.

The Markdown and PDF versions contain the same report. Ten focused implementation tests passed in the completed benchmark work; no additional inference spend was needed to prepare this report.
