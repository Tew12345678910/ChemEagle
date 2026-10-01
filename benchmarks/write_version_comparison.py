"""Write a provenance-aware comparison of GitHub, all-cloud, and optimized paths."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]

def main():
    d=json.loads((ROOT/'reports/version_comparison.json').read_text())
    github=d['github_proxy'];cloud=d['cloud_worker'];sol=d['sol_review'];lite=d['lite']
    def row(label,s):
        price=s['estimated_usd'];cost='Unavailable' if price is None else f'USD {price:.3f}'
        return f"| {label} | {s['successful_images']}/73 | {s['soft_match']['f1']:.3f} | {s['exact_match']['f1']:.3f} | {s['mean_seconds']:.1f} | {cost} |"
    def pr(s):return f"{s['soft_match']['precision']:.3f} / {s['soft_match']['recall']:.3f}"
    cost_saved=100*(1-lite['estimated_usd']/sol['estimated_usd'])
    cloud_cost_delta=100*(lite['estimated_usd']/cloud['estimated_usd']-1)
    cloud_latency_delta=100*(lite['mean_seconds']/cloud['mean_seconds']-1)
    text=f'''# ChemEAGLE: GitHub, all-cloud and cost-optimized comparison

This report compares the original GitHub-style hybrid pipeline, the current all-cloud Worker implementation, and the optimized cloud-model pipeline on 73 R-group figures containing 893 labelled reactions. A separate Sol-only experiment is included to correct the provenance of the earlier report.

## What the versions mean

**1. GitHub hybrid.** The reference repository combines LLM planning and extraction agents with local specialist tools, including RxnIM, MolNexTR, OCR and chemical recognition checkpoints. A cloud-hosted LLM does not make this an all-cloud implementation: the specialist models still run on the host GPU. Your fork's main commit is `54276de`; the current author repository is `6fea3e1`. The author repository now defaults to Gemini 3.7 Flash through its shared client, while retaining the specialist pipeline.

**2. All-cloud Worker.** `ChemEagle-Cloud` commit `88ebf7a` implements an image-only Worker using one model extraction request followed by a second image-grounded validation request. It contains no Torch, RDKit, RxnIM, MolNexTR or local model weights. The web interface defaults to Gemini 3.7 Flash. Its prompts and parser were benchmarked unchanged, with validation enabled and original PNG bytes, directly against HKUST. This tests the extraction algorithm; it does not measure the deployed Worker or web application's latency.

**3. Cloud models with cost optimization.** The optimized variant sends one bounded-resolution image to Gemini 3.7 Flash, runs deterministic RDKit checks, and requests GPT-5.6 Sol high visual review only when flagged. It also caches clean results. All model inference is remote, but RDKit validation and orchestration run on a CPU host. This variant is not yet a deployment of the pure Cloudflare Worker and has not been integrated into its web interface.

## Three-version benchmark

| Version | Successful images | F1 | Exact F1 | Mean seconds/image | Reference token cost |
|---|---:|---:|---:|---:|---:|
{row('GitHub-style hybrid, historical compatibility run',github)}
{row('Current all-cloud Worker, Gemini two-pass',cloud)}
{row('Cloud models with selective Sol review',lite)}

Precision / recall were **{pr(github)}** for the historical hybrid, **{pr(cloud)}** for the current cloud Worker, and **{pr(lite)}** for the optimized variant. F1 is a precision/recall measure; it is not the percentage of fully correct images.

The GitHub-style result is a historical compatibility benchmark from 10-11 September, rescored with today's evaluator. It used the normal hybrid source on an SSH host with RTX 3090 GPUs, but a benchmark shim replaced unavailable GPT-4o calls with GPT-5 Mini and removed unsupported sampling parameters. Four images failed. Therefore, F1 {github['soft_match']['f1']:.3f} is **not an exact benchmark of the published GPT-4o configuration**, and is not a run of the author's latest Gemini-default commit. No valid token-cost record exists for it; GPU, host and external-service costs are also unavailable. Do not interpret this row as the paper's published accuracy.

The current cloud Worker was freshly benchmarked on 1 October, using its pinned payload builders and output normalizer. The optimized results are the completed 1 October run. All three rows cover the same 73 images and ground truth. They differ in prompts, model choice, image resolution and execution environment, so the table compares whole configurations rather than isolating the effect of hosting alone.

## Correction to the earlier saved baseline

The earlier report called F1 0.815 the saved ChemEagle baseline. Its provenance is a **standalone all-cloud Sol experiment**, not the original GitHub specialist pipeline and not the current Cloud Worker's Gemini implementation. The experiment used GPT-5.6 Sol medium extraction followed by Sol high review of the full image plus three overlapping crops, with a row-count fallback gate. It was run on 21 September and rescored today.

| Configuration | F1 | Exact F1 | Mean seconds/image | Reference token cost |
|---|---:|---:|---:|---:|
| Saved all-cloud Sol medium + high review | {sol['soft_match']['f1']:.3f} | {sol['exact_match']['f1']:.3f} | {sol['mean_seconds']:.1f} | USD {sol['estimated_usd']:.3f} |
| Optimized Gemini + selective Sol review | {lite['soft_match']['f1']:.3f} | {lite['exact_match']['f1']:.3f} | {lite['mean_seconds']:.1f} | USD {lite['estimated_usd']:.3f} |

The **{cost_saved:.1f}% estimated token-cost saving** refers specifically to this Sol experiment. The corresponding latency reduction is {100*(1-lite['mean_seconds']/sol['mean_seconds']):.1f}%. It should not be quoted as a measured saving against the original GitHub version.

Compared with the current Gemini two-pass Cloud Worker, the optimized variant changes reference cost by **{cloud_cost_delta:+.1f}%**, mean latency by **{cloud_latency_delta:+.1f}%**, and F1 by **{lite['soft_match']['f1']-cloud['soft_match']['f1']:+.3f}**. Negative percentages mean lower cost or latency. These are single-run observations, not controlled estimates of causal effects.

## Why the optimized configuration differs

The Sol experiment made 146 model calls for 73 images. The optimized variant needed 73 Flash extraction calls and five Sol reviews: 78 calls in total. Local checks flagged invalid SMILES, wildcard atoms, empty outputs and duplicate rows. Accepted reviews preserved row counts and row identities and did not increase invalid structures or duplicates.

The optimized result contained zero invalid SMILES among 2,543 molecular entries, compared with six invalid entries in the saved Sol experiment. Syntax validity does not establish agreement with the chemical drawing. The current cloud Worker had {cloud['invalid_smiles']} invalid or missing SMILES entries and the historical GitHub-compatible run had {github['invalid_smiles']}, using the same local scoring-time validator.

Caching was verified with a live smoke test: the first identical input made one paid model call, and the second made zero. Cache keys include image contents, prompt, model, reasoning, resolution and review policy. The reported benchmark prices describe cold extraction, not repeated cache hits.

## Other models and settings

| Configuration | Successful images | F1 | Exact F1 | Mean seconds/image | Reference token cost |
|---|---:|---:|---:|---:|---:|
'''
    comparison=json.loads((ROOT/'reports/full-economical.json').read_text())['models']
    normal=json.loads((ROOT/'reports/full-gemini-default.json').read_text())['models']
    kimi=json.loads((ROOT/'reports/full-kimi-no-reasoning.json').read_text())['models']
    entries=[('Gemini 3.7 Flash, default reasoning',normal['gemini-3.7-flash']),('Gemini 3.7 Flash, low reasoning',comparison['gemini-3.7-flash']),('Kimi K3, reasoning off',kimi['moonshotai/kimi-k3']),('Qwen 3.8 Flash service, reasoning off',comparison['qwen/qwen3.8-flash']),('MiniMax M3, reasoning off',comparison['minimax/minimax-m3'])]
    text+='\n'.join(row(n,s) for n,s in entries)
    text+='''

These are separate direct image-to-SMILES configurations using the optimized extraction prompt, not replacements tested inside the original GitHub specialist pipeline or the current Cloud Worker. The inexpensive Kimi and MiniMax open-weight routes lost substantial accuracy; Qwen Flash was also tested, but its weight availability was not verified. Low price alone does not support replacing ChemEagle with these direct-conversion configurations.

## Measurement limits

GT4 contains 78 rows, but only 73 matching images are available. The sole existing colon-to-underscore filename mismatch was normalized. Failed responses contribute zero predictions while retaining their ground truth in recall. Conditions, PDF segmentation and document-level extraction are outside the scored task.

Benchmark F1 uses the existing 0.5 reactant/product overlap rule. Exact F1 requires complete matching reactant and product multisets. Both canonicalize SMILES, strip stereochemistry and retain the largest salt fragment. Exact F1 therefore does not certify exact stereochemistry or complete salt identity.

USD figures reprice measured token usage with the same 1 October OpenRouter catalog. They are reference estimates, not HKUST invoices, and include reported reasoning tokens. Unknown token usage cannot be reconstructed. Latency is observed per-image extraction time under each run's workload; sums are not elapsed batch duration. GPU hosting and infrastructure costs are excluded.

The optimized images were bounded to 1,800 pixels on the longest side; the current Cloud Worker benchmark used original PNGs. The selective-review policy was developed on a 12-image subset reused in the full benchmark. The small F1 gain over Sol does not establish statistical superiority, and no independent held-out dataset has been evaluated.

All new model inference calls used the HKUST chat-completions endpoint. OpenRouter supplied public pricing only. GPT-6 Sol and GPT-6.1 Sol were absent from the HKUST catalog checked on 1 October and were not benchmarked. Yufan's email has not been verified.

## Recommendation

For this R-group workload, use Gemini default reasoning with selective Sol review when comparable quality to the Sol experiment is required at lower estimated cost. Retain the original specialist pipeline for tasks outside the tested scope. Validate the optimized variant on independent images, including stereochemistry and salts, before making it the production default. Integrating the CPU validator into the deployed cloud service is a separate step.

## Code references

- [Your GitHub reference fork, commit 54276de](https://github.com/Tew12345678910/ChemEagle/tree/54276de6a7d3210e4f4d42f605cb6b17bfd5d1ba).
- [Author's current GitHub implementation, commit 6fea3e1](https://github.com/CYF2000127/ChemEagle/tree/6fea3e1f1fcb54803471522b3327c6ef15a88063).
- [All-cloud Worker, commit 88ebf7a](https://github.com/Tew12345678910/ChemEagle-Cloud/tree/88ebf7a2080a4ab3ab22c7101cf67e9c1de407e1/cloud_worker).
- [Cost-optimized branch](https://github.com/Tew12345678910/ChemEagle/tree/mathus/chemeagle-cost-optimized).
- [Common reference pricing catalog](https://openrouter.ai/api/v1/models), snapshot dated 1 October 2026.
'''
    (ROOT/'reports/cost_optimization_2026-10-01.md').write_text(text)

if __name__=='__main__':main()
