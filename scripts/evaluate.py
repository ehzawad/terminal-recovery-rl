"""Run one policy configuration over a rows file (see make_rows.py) and summarise it.

Each row is one episode; results are appended to --out (resumable). The summary reports the
primary outcome (macro-averaged complete success), mean partial credit, the recovery-failure
incidence on faulted episodes where the fault was observed, informative-group share, and cost.

Usage:
  python scripts/evaluate.py --rows data/rows/dev_search_train.jsonl --out runs/eval/P0.jsonl \
      [--model q9 | --model <lora-name>] [--system-prompt-file prompts/p3.txt] [--check-revise]
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

from termrl.config import MODEL_PATH, SYSTEM_DEFAULT
from termrl.rollout import Renderer, run_episode


def seed_for(task_id: str, trial: int) -> int:
    return int(hashlib.sha256(f"{task_id}:{trial}".encode()).hexdigest()[:8], 16)


def summarize(rows: list[dict]) -> dict:
    by_task = collections.defaultdict(list)
    for r in rows:
        by_task[r["task_id"]].append(r)
    per_task = {t: statistics.mean(bool(x.get("verdict", {}).get("success")) for x in rs) for t, rs in by_task.items()}
    faulted = [r for r in rows if r.get("fault")]
    observed = [r for r in faulted if r.get("fault_observed_call") is not None]
    rec_fail = [r for r in observed if not r.get("verdict", {}).get("success")]
    uncleared = [r for r in observed if r.get("fault_cleared") is False]
    groups_var = sum(1 for rs in by_task.values() if len({round(x.get("verdict", {}).get("reward", 0.0), 6) for x in rs}) > 1)
    groups_mixed = sum(1 for rs in by_task.values() if 0 < sum(bool(x.get("verdict", {}).get("success")) for x in rs) < len(rs))
    by_family = collections.defaultdict(list)
    for r in rows:
        by_family[(r.get("fault") or {}).get("family", "clean")].append(bool(r.get("verdict", {}).get("success")))
    return {
        "episodes": len(rows), "tasks": len(by_task),
        "success_macro": round(statistics.mean(per_task.values()), 4) if per_task else None,
        "partial_mean": round(statistics.mean(r.get("verdict", {}).get("reward", 0.0) for r in rows), 4) if rows else None,
        "success_by_family": {k: round(statistics.mean(v), 3) for k, v in sorted(by_family.items())},
        "fault_observed_rate": round(len(observed) / len(faulted), 3) if faulted else None,
        "recovery_failure_incidence": round(len(rec_fail) / len(observed), 3) if observed else None,
        "fault_left_uncleared": round(len(uncleared) / len(observed), 3) if observed else None,
        "informative_groups_semantic": f"{groups_var}/{len(by_task)}",
        "mixed_success_groups": f"{groups_mixed}/{len(by_task)}",
        "end_reasons": dict(collections.Counter(r.get("end_reason") for r in rows)),
        "harness_errors": sum(1 for r in rows if r.get("harness_error") or r.get("verdict", {}).get("error")),
        "gen_tokens_mean": round(statistics.mean(r.get("generated_tokens", 0) for r in rows)) if rows else None,
        "turns_mean": round(statistics.mean(len(r.get("turns", [])) for r in rows), 2) if rows else None,
        "seconds_mean": round(statistics.mean(r.get("seconds", 0) for r in rows), 1) if rows else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="q9")
    ap.add_argument("--system-prompt-file")
    ap.add_argument("--check-revise", action="store_true")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--temperature", type=float, default=0.7, help="0.7 for evaluation; 1.0 to collect SFT data")
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--base-url", default="http://127.0.0.1:8765/v1")
    args = ap.parse_args()

    rows_in = [json.loads(l) for l in open(args.rows)]
    system_prompt = open(args.system_prompt_file).read().strip() if args.system_prompt_file else SYSTEM_DEFAULT
    client = OpenAI(base_url=args.base_url, api_key="none", timeout=900)
    renderer = Renderer(MODEL_PATH)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    results, done = [], set()
    if os.path.exists(args.out):
        for line in open(args.out):
            r = json.loads(line)
            results.append(r)
            done.add((r["task_id"], r["trial"]))
    todo = [r for r in rows_in if (r["task_id"], r["trial"]) not in done]
    lock = threading.Lock()

    def work(row):
        tr = run_episode(client, renderer, args.model, row["task_root"], system_prompt=system_prompt,
                         seed=seed_for(row["task_id"], row["trial"]), fault_family=row.get("fault_family"),
                         fault_seed=row.get("fault_seed", 0), check_revise=args.check_revise,
                         temperature=args.temperature, top_p=args.top_p, top_k=args.top_k)
        tr.update({"task_id": row["task_id"], "trial": row["trial"], "partition": row.get("partition"),
                   "arm_model": args.model, "prompt_file": args.system_prompt_file})
        with lock:
            with open(args.out, "a") as f:
                f.write(json.dumps(tr) + "\n")
            results.append(tr)
            v = tr.get("verdict", {})
            print(f"[{len(results)}/{len(rows_in)}] {row['task_id']} t{row['trial']} {row.get('fault_family') or 'clean'} "
                  f"ok={v.get('success')} r={v.get('reward', 0):.2f} end={tr['end_reason']} "
                  f"obs={tr.get('fault_observed_call')} cleared={tr.get('fault_cleared')} turns={len(tr['turns'])}", flush=True)

    with cf.ThreadPoolExecutor(args.concurrency) as ex:
        list(ex.map(work, todo))
    summary = summarize(results)
    print(json.dumps(summary, indent=1))
    with open(args.out.replace(".jsonl", ".summary.json"), "w") as f:
        json.dump(summary, f, indent=1)


if __name__ == "__main__":
    main()
