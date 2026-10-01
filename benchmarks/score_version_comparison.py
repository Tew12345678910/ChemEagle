"""Rescore identical benchmark inputs, preserving version provenance."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from efficient import atomic_json
from report_efficient import describe
from legacy_score import ground_truth_by_image
from rdkit import RDLogger


def main():
    RDLogger.DisableLog('rdApp.*')
    out=ROOT/'benchmark-runs/cloud-current'
    cloud=json.loads((out/'aggregate.json').read_text())
    if len(cloud['runs'])!=73 or cloud.get('status')!='completed':raise SystemExit('Cloud benchmark must finish before publishing comparison')
    gt=ground_truth_by_image(Path('/Users/mathus/Downloads/r_group_resolution_diagrams/GT4.json'))
    catalog=json.loads((ROOT/'reports/openrouter_catalog_2026-10-01.json').read_text())
    selected=set(cloud['images'])
    source=Path('/Users/mathus/.codex/visualizations/2026/09/10/01a08a46-483e-78c2-9d38-62dd955b87d0')
    original=json.loads((source/'normal_full_aggregate.json').read_text())
    if {r['image'] for r in original['runs']}!=selected:raise SystemExit('Historical image inventory mismatch')
    github=describe(original['runs'],gt,None)
    cloud_score=describe(cloud['runs'],gt,catalog['google/gemini-3.7-flash']['pricing'],catalog)
    known=json.loads((ROOT/'reports/selective-review.json').read_text())['models']
    for key in ['saved_sol_medium_high_review','gemini-3.7-flash-selective-sol-review']:
        if {r['image'] for r in known[key]['per_image']}!=selected:raise SystemExit('Optimized/Sol image inventory mismatch')
    values={'github_proxy':github,'cloud_worker':cloud_score,'sol_review':known['saved_sol_medium_high_review'],'lite':known['gemini-3.7-flash-selective-sol-review']}
    atomic_json(out/'version_scores.json',values)
    atomic_json(ROOT/'reports/version_comparison.json',values)
    for name,s in values.items():print(name,s['successful_images'],s['soft_match']['f1'],s['exact_match']['f1'],s['mean_seconds'],s['estimated_usd'])

if __name__=='__main__':main()
