"""Headroom probe: run the served policy on a task list with K fresh trials each.

Writes one JSON line per trial (full trace) and prints the per-task success table,
the share of task groups with non-zero reward variance, and token/turn statistics.

Usage:
  python scripts/probe.py --tasks data/probe_tasks.txt --trials 4 --out runs/probe_base.jsonl \
      [--thinking] [--system-prompt-file prompts/x.txt] [--concurrency 8]
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

from termrl.agent import SYSTEM_DEFAULT, run_episode


def seed_for(task_root: str, trial: int) -> int:
    return int(hashlib.sha256(f"{os.path.basename(task_root)}:{trial}".encode()).hexdigest()[:8], 16)


def summarize(rows: list[dict]) -> None:
    by_task = collections.defaultdict(list)
    for r in rows:
        by_task[os.path.basename(r["task_root"])].append(r)
    succ, informative_bin, informative_partial = [], 0, 0
    for tid, rs in sorted(by_task.items()):
        s = [bool(r.get("verdict", {}).get("success")) for r in rs]
        rw = [r.get("verdict", {}).get("reward", 0.0) for r in rs]
        succ.append(sum(s) / len(s))
        informative_bin += 0 < sum(s) < len(s)
        informative_partial += len(set(round(x, 6) for x in rw)) > 1
    n = len(by_task)
    trials = len(rows)
    ends = collections.Counter(r["end_reason"] for r in rows)
    errs = sum(1 for r in rows if r.get("verdict", {}).get("error") or r.get("harness_error"))
    toks = [r["generated_tokens"] for r in rows]
    turns = [len(r["turns"]) for r in rows]
    print(f"tasks={n} trials={trials} mean_success={statistics.mean(succ):.3f} "
          f"mean_partial={statistics.mean(r.get('verdict', {}).get('reward', 0.0) for r in rows):.3f}")
    print(f"per-task successes histogram (share of trials): {collections.Counter(round(x, 2) for x in succ).most_common()}")
    print(f"informative groups: binary {informative_bin}/{n} ({informative_bin / n:.0%}), partial {informative_partial}/{n} ({informative_partial / n:.0%})")
    print(f"end reasons {dict(ends)}; verifier/harness errors {errs}")
    print(f"generated tokens: mean {statistics.mean(toks):.0f} p50 {statistics.median(toks):.0f} max {max(toks)}; "
          f"turns mean {statistics.mean(turns):.1f} max {max(turns)}; seconds mean {statistics.mean(r['seconds'] for r in rows):.1f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--trials", type=int, default=4)
    ap.add_argument("--out", required=True)
    ap.add_argument("--thinking", action="store_true")
    ap.add_argument("--system-prompt-file")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--max-turns", type=int, default=20)
    ap.add_argument("--max-generated-tokens", type=int, default=12000)
    ap.add_argument("--base-url", default="http://127.0.0.1:8765/v1")
    ap.add_argument("--model", default="q9")
    args = ap.parse_args()

    roots = [l.strip() for l in open(args.tasks) if l.strip() and not l.startswith("#")]
    system_prompt = open(args.system_prompt_file).read().strip() if args.system_prompt_file else SYSTEM_DEFAULT
    client = OpenAI(base_url=args.base_url, api_key="none", timeout=900)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    done = set()
    rows = []
    if os.path.exists(args.out):  # resume: skip trials already recorded
        for line in open(args.out):
            r = json.loads(line)
            rows.append(r)
            done.add((r["task_root"], r["trial"]))
    jobs = [(root, k) for root in roots for k in range(args.trials) if (root, k) not in done]
    lock = threading.Lock()

    def work(job):
        root, k = job
        tr = run_episode(client, args.model, root, system_prompt=system_prompt, enable_thinking=args.thinking,
                         max_turns=args.max_turns, max_generated_tokens=args.max_generated_tokens,
                         seed=seed_for(root, k))
        tr["trial"] = k
        with lock:
            with open(args.out, "a") as f:
                f.write(json.dumps(tr) + "\n")
            rows.append(tr)
            v = tr.get("verdict", {})
            print(f"[{len(rows)}/{len(roots) * args.trials}] {os.path.basename(root)} t{k} "
                  f"success={v.get('success')} reward={v.get('reward', 0):.2f} end={tr['end_reason']} "
                  f"turns={len(tr['turns'])} tok={tr['generated_tokens']} {tr['seconds']:.0f}s", flush=True)

    with cf.ThreadPoolExecutor(args.concurrency) as ex:
        list(ex.map(work, jobs))
    summarize(rows)


if __name__ == "__main__":
    main()
