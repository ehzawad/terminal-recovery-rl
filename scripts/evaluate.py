"""Run one policy configuration over a rows file (see make_rows.py) and summarise it.

Each row is one episode keyed by `row_id`; results are appended to --out and the run resumes only
if the file was produced under the identical configuration (rows file, prompt, model, decoding,
controller, harness version) -- otherwise it refuses. The summary reports every registered quantity
with its denominator:
  safe_success_faulted / safe_success_clean   macro over tasks within each episode type
  collateral_clean                            share of clean episodes with a collateral modification
  recovery_failure_observed                   faulted episodes with the fault observed that failed
  failure_assigned_fault                      all faulted episodes that failed (no observation filter)
  group variance                              per configuration (row groups of repeated attempts)

Usage:
  python scripts/evaluate.py --rows data/rows/x.jsonl --out runs/eval/y.jsonl \
      --system-prompt-file prompts/pX.txt [--model q9|<lora>] [--check-revise] [--temperature ...]
"""

import argparse
import collections
import concurrent.futures as cf
import hashlib
import json
import os
import statistics
import threading

from openai import OpenAI

from termrl.config import MODEL_PATH
from termrl.rollout import Renderer, run_episode


def seed_for(row_id: str) -> int:
    return int(hashlib.sha256(row_id.encode()).hexdigest()[:8], 16)


def sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]


def _rate(xs) -> float | None:
    xs = list(xs)
    return round(statistics.mean(xs), 4) if xs else None


def _macro(rows, key) -> float | None:
    by = collections.defaultdict(list)
    for r in rows:
        by[r["task_id"]].append(float(key(r)))
    return round(statistics.mean(statistics.mean(v) for v in by.values()), 4) if by else None


def summarize(rows: list[dict]) -> dict:
    assigned = lambda r: r.get("assigned_fault", (r.get("fault") or {}).get("family"))
    faulted = [r for r in rows if assigned(r)]
    clean = [r for r in rows if not assigned(r)]
    observed = [r for r in faulted if r.get("fault_observed_call") is not None]
    groups = collections.defaultdict(list)
    for r in rows:
        groups[(r["task_id"], r.get("config"))].append(r)
    multi = {k: g for k, g in groups.items() if len(g) > 1}
    by_family = collections.defaultdict(list)
    for r in rows:
        by_family[(r.get("fault") or {}).get("family", "clean")].append(bool(r.get("safe_success")))
    return {
        "episodes": len(rows), "tasks": len({r["task_id"] for r in rows}),
        "faulted_episodes": len(faulted), "clean_episodes": len(clean), "observed_faulted_episodes": len(observed),
        "safe_success_macro": _macro(rows, lambda r: r.get("safe_success")),
        "safe_success_faulted": _macro(faulted, lambda r: r.get("safe_success")),
        "safe_success_clean": _macro(clean, lambda r: r.get("safe_success")),
        "success_macro": _macro(rows, lambda r: (r.get("verdict") or {}).get("success")),
        "collateral_clean": _rate(r.get("collateral") is not None for r in clean),
        "collateral_all": _rate(r.get("collateral") is not None for r in rows),
        "fabricated_input": _rate(bool(r.get("fabricated_input")) for r in faulted),
        "recovery_failure_observed": _rate(not (r.get("verdict") or {}).get("success") for r in observed),
        "failure_assigned_fault": _rate(not r.get("safe_success") for r in faulted),
        "fault_observed_rate": _rate(r.get("fault_observed_call") is not None for r in faulted),
        "safe_success_by_family": {k: round(statistics.mean(v), 3) for k, v in sorted(by_family.items())},
        "groups_with_repeats": len(multi),
        "groups_reward_varies": sum(1 for g in multi.values() if len({round(r.get("reward", 0.0), 6) for r in g}) > 1),
        "groups_mixed_safe_success": sum(1 for g in multi.values()
                                         if 0 < sum(bool(r.get("safe_success")) for r in g) < len(g)),
        "no_command_episodes": sum(1 for r in rows if not r.get("commands")),
        "harness_errors": sum(1 for r in rows if r.get("harness_error") or (r.get("verdict") or {}).get("error")),
        "end_reasons": dict(collections.Counter(r.get("end_reason") for r in rows)),
        "reward_mean": _rate(r.get("reward", 0.0) for r in rows),
        "gen_tokens_mean": statistics.mean(r.get("generated_tokens", 0) for r in rows) if rows else None,
        "turns_mean": round(statistics.mean(len(r.get("turns", [])) for r in rows), 2) if rows else None,
        "seconds_mean": round(statistics.mean(r.get("seconds", 0) for r in rows), 1) if rows else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--system-prompt-file", required=True)
    ap.add_argument("--model", default="q9")
    ap.add_argument("--check-revise", action="store_true")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--temperature", type=float, default=0.7, help="0.7 for evaluation; 1.0 to collect SFT data")
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--base-url", default="http://127.0.0.1:8765/v1")
    args = ap.parse_args()

    rows_in = [json.loads(l) for l in open(args.rows)]
    ids = [r["row_id"] for r in rows_in]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate row_id in rows file")
    system_prompt = open(args.system_prompt_file).read().strip()
    identity = {"rows_sha": sha(args.rows), "prompt_sha": sha(args.system_prompt_file), "model": args.model,
                "check_revise": args.check_revise, "temperature": args.temperature, "top_p": args.top_p,
                "top_k": args.top_k, "harness": "v4.1"}
    client = OpenAI(base_url=args.base_url, api_key="none", timeout=900)
    renderer = Renderer(MODEL_PATH)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    results, done = [], set()
    if os.path.exists(args.out):
        for line in open(args.out):
            r = json.loads(line)
            if r.get("identity") != identity:
                raise SystemExit(f"{args.out} was produced under a different configuration; refusing to resume")
            results.append(r)
            done.add(r["row_id"])
    todo = [r for r in rows_in if r["row_id"] not in done]
    lock = threading.Lock()

    def work(row):
        tr = run_episode(client, renderer, args.model, row["task_root"], system_prompt=system_prompt,
                         seed=seed_for(row["row_id"]), fault_family=row.get("fault_family"),
                         fault_seed=row.get("fault_seed", 0), check_revise=args.check_revise,
                         temperature=args.temperature, top_p=args.top_p, top_k=args.top_k)
        tr.update({k: row[k] for k in ("row_id", "task_id", "config", "attempt", "trial", "partition")},
                  identity=identity, assigned_fault=row.get("fault_family"))
        with lock:
            with open(args.out, "a") as f:
                f.write(json.dumps(tr) + "\n")
            results.append(tr)
            v = tr.get("verdict") or {}
            print(f"[{len(results)}/{len(rows_in)}] {row['row_id']} {row.get('fault_family') or 'clean'} "
                  f"safe={tr.get('safe_success')} r={tr.get('reward', 0):.2f} end={tr['end_reason']} "
                  f"obs={tr.get('fault_observed_call')} coll={tr.get('collateral') is not None} "
                  f"turns={len(tr['turns'])}" + (" HARNESS_ERROR" if tr.get("harness_error") else ""), flush=True)

    with cf.ThreadPoolExecutor(args.concurrency) as ex:
        list(ex.map(work, todo))
    summary = summarize(results)
    summary["identity"] = identity
    print(json.dumps(summary, indent=1))
    with open(args.out.replace(".jsonl", ".summary.json"), "w") as f:
        json.dump(summary, f, indent=1)


if __name__ == "__main__":
    main()
