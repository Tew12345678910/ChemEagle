"""Review only locally flagged successful predictions; never send ground truth."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
from efficient import atomic_json, validate
from efficient_review import refine


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--env-file", type=Path, required=True)
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()
    env = dotenv_values(args.env_file)
    key = env.get("NEW_API_KEY") or env.get("API_KEY")
    if not key:
        raise SystemExit("No HKUST key configured")
    source = json.loads(args.source.read_text())
    data = copy.deepcopy(source)
    data["backend"] = "gemini-3.7-flash-selective-sol-review"
    data["source"] = str(args.source)
    finished = json.loads(args.output.read_text()) if args.output.exists() else {"runs": []}
    reviewed = {r["image"]: r for r in finished["runs"] if r.get("result", {}).get("meta", {}).get("review", {}).get("requested")}
    def process(run):
        draft = run["result"]["results"][0]
        result, meta = refine(args.input_dir / run["image"], draft, key)
        out = copy.deepcopy(run)
        out["wall_seconds"] += meta["wall_seconds"]
        out["result"]["results"] = [result]
        original = out["result"]["meta"]
        out["result"]["meta"] = {"source_usage": original["usage"], "source_model": original["requested_model"],
                                 "review": meta, "validation": validate(result)}
        return out
    pending = [r for r in source["runs"] if r["exit_code"] == 0
               and validate(r["result"]["results"][0])["needs_review"] and r["image"] not in reviewed]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(process, r) for r in pending]):
            out = future.result()
            reviewed[out["image"]] = out
            data["runs"] = [reviewed.get(r["image"], r) for r in source["runs"]]
            atomic_json(args.output, data)
            print(out["image"], out["result"]["meta"]["review"]["accepted"], flush=True)
    data["runs"] = [reviewed.get(r["image"], r) for r in source["runs"]]
    data["review_requests"] = len(reviewed)
    data["status"] = source["status"]
    atomic_json(args.output, data)


if __name__ == "__main__":
    main()
