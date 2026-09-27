"""Arm S: two rounds of self-generated, verifier-filtered multi-turn SFT (expert iteration; A1, A5).

S and R share one set of 256 training configurations (make_rows salt 'train-v4', 75/25 clean/faulted
on faultable tasks). R trains on all 256 as GRPO groups of four; S spends the same 1,024 attempts:
round 1 = configurations 0-127 x 4 attempts of the instruct model with P's prompt at the RL sampling
distribution; SFT from the instruct weights on the *safe* successes -> r1/epoch1, r1/epoch2.
round 2 = configurations 128-255 x 4 attempts of r1/epoch2; SFT from the instruct weights on the union
of both rounds' safe successes -> r2/epoch1, r2/epoch2. The four checkpoints are candidates for
dev_monitor selection. One 18 GPU-hour cap covers collection and fitting together.

Usage: python scripts/run_arm_s.py --prompt-file prompts/pX.txt [--out runs/S_seed1]
"""

import argparse
import json
import os
import subprocess
import sys
import time

from termrl import server

PY = sys.executable


def rows(skip: int, out: str) -> str:
    subprocess.run([PY, "scripts/make_rows.py", "--partition", "train", "--families", "mix", "--fault-share", "0.25",
                    "--salt", "train-v4", "--skip", str(skip), "--limit", "128", "--attempts", "4", "--out", out],
                   check=True)
    return out


def collect(rows_path: str, out: str, prompt: str, model: str, lora: dict | None) -> list[dict]:
    proc = server.start(lora, log_path=f"{os.path.dirname(out)}/vllm.log")
    try:
        subprocess.run([PY, "scripts/evaluate.py", "--rows", rows_path, "--out", out, "--model", model,
                        "--system-prompt-file", prompt, "--temperature", "1.0", "--top-p", "1.0", "--top-k", "-1",
                        "--concurrency", "8"], check=True)
    finally:
        server.stop(proc)
    return [json.loads(l) for l in open(out)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--out", default="runs/S_seed1")
    ap.add_argument("--max-hours", type=float, default=18.0)
    args = ap.parse_args()
    o = args.out
    os.makedirs(o, exist_ok=True)
    t0 = time.time()
    left = lambda: args.max_hours - (time.time() - t0) / 3600
    ledger = {"prompt_file": args.prompt_file}

    r1 = collect(rows(0, f"{o}/r1_rows.jsonl"), f"{o}/r1_rollouts.jsonl", args.prompt_file, "q9", None)
    ledger["round1"] = {"attempts": len(r1), "safe_successes": sum(bool(t.get("safe_success")) for t in r1),
                        "hours_after_collection": round((time.time() - t0) / 3600, 2)}
    subprocess.run([PY, "scripts/train_sft.py", "--data", f"{o}/r1_rollouts.jsonl", "--out", f"{o}/r1",
                    "--max-hours", f"{max(0.25, left() / 3):.2f}"], check=True)
    ledger["round1"]["hours_after_fit"] = round((time.time() - t0) / 3600, 2)

    r2 = collect(rows(128, f"{o}/r2_rows.jsonl"), f"{o}/r2_rollouts.jsonl", args.prompt_file, "s1",
                 {"s1": f"{o}/r1/epoch2"})
    ledger["round2"] = {"attempts": len(r2), "safe_successes": sum(bool(t.get("safe_success")) for t in r2),
                        "hours_after_collection": round((time.time() - t0) / 3600, 2)}
    subprocess.run([PY, "scripts/train_sft.py", "--data", f"{o}/r1_rollouts.jsonl", "--data", f"{o}/r2_rollouts.jsonl",
                    "--out", f"{o}/r2", "--max-hours", f"{max(0.25, left()):.2f}"], check=True)
    ledger["total_hours"] = round((time.time() - t0) / 3600, 2)
    ledger["within_cap"] = ledger["total_hours"] <= args.max_hours
    ledger["candidates"] = [p for p in (f"{o}/r1/epoch1", f"{o}/r1/epoch2", f"{o}/r2/epoch1", f"{o}/r2/epoch2")
                            if os.path.isdir(p)]
    json.dump(ledger, open(f"{o}/summary.json", "w"), indent=1)
    print(json.dumps(ledger, indent=1))


if __name__ == "__main__":
    main()
