"""Arm S: two rounds of self-generated, verifier-filtered multi-turn SFT (expert iteration).

Round 1: 512 attempts of the instruct model with P's prompt on train rows (75% clean with planted
fixtures, 25% training-family faults) at the RL sampling distribution (temperature 1.0, top-p 1.0,
no top-k); keep *safe* successes (complete success, no collateral modification); SFT from the
instruct weights -> checkpoints r1/epoch1, r1/epoch2.
Round 2: 512 fresh attempts of r1/epoch2; SFT from the instruct weights on the union of both
rounds' safe successes -> r2/epoch1, r2/epoch2. The four checkpoints are the candidates chosen on
dev_monitor. Every attempt counts against the budget, failures included.

Usage: python scripts/run_arm_s.py --prompt-file prompts/pX.txt [--out runs/S_seed1]
"""

import argparse
import json
import os
import subprocess
import sys

from termrl import server

PY = sys.executable


def collect(rows: str, out: str, prompt: str, model: str, lora: dict | None) -> list[dict]:
    proc = server.start(lora, log_path=f"{os.path.dirname(out)}/vllm.log")
    try:
        subprocess.run([PY, "scripts/evaluate.py", "--rows", rows, "--out", out, "--model", model,
                        "--system-prompt-file", prompt, "--temperature", "1.0", "--top-p", "1.0", "--top-k", "-1",
                        "--concurrency", "8"], check=True)
    finally:
        server.stop(proc)
    return [json.loads(l) for l in open(out)]


def safe_successes(traces: list[dict], path: str) -> int:
    keep = [t for t in traces if t.get("safe_success") and not t.get("harness_error")]
    with open(path, "w") as f:
        for t in keep:
            f.write(json.dumps(t) + "\n")
    return len(keep)


def rows_slice(trials: tuple[int, int], out: str, limit: int) -> str:
    tmp = out + ".all"
    subprocess.run([PY, "scripts/make_rows.py", "--partition", "train", "--trials", str(trials[1]),
                    "--families", "mix", "--fault-share", "0.25", "--out", tmp], check=True)
    rows = [json.loads(l) for l in open(tmp) if trials[0] <= json.loads(l)["trial"] < trials[1]]
    os.remove(tmp)
    with open(out, "w") as f:
        for r in rows[:limit]:
            f.write(json.dumps(r) + "\n")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--out", default="runs/S_seed1")
    ap.add_argument("--attempts-per-round", type=int, default=512)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    o = args.out

    r1_rows = rows_slice((0, 2), f"{o}/r1_rows.jsonl", args.attempts_per_round)
    r1 = collect(r1_rows, f"{o}/r1_rollouts.jsonl", args.prompt_file, "q9", None)
    n1 = safe_successes(r1, f"{o}/r1_safe.jsonl")
    print(f"round 1: {n1}/{len(r1)} safe successes", flush=True)
    subprocess.run([PY, "scripts/train_sft.py", "--data", f"{o}/r1_safe.jsonl", "--out", f"{o}/r1"], check=True)

    r2_rows = rows_slice((2, 4), f"{o}/r2_rows.jsonl", args.attempts_per_round)
    r2 = collect(r2_rows, f"{o}/r2_rollouts.jsonl", args.prompt_file, "s1", {"s1": f"{o}/r1/epoch2"})
    n2 = safe_successes(r2, f"{o}/r2_safe.jsonl")
    print(f"round 2: {n2}/{len(r2)} safe successes", flush=True)
    subprocess.run([PY, "scripts/train_sft.py", "--data", f"{o}/r1_safe.jsonl", "--data", f"{o}/r2_safe.jsonl",
                    "--out", f"{o}/r2"], check=True)
    json.dump({"round1": {"attempts": len(r1), "safe_successes": n1}, "round2": {"attempts": len(r2), "safe_successes": n2},
               "candidates": [f"{o}/r1/epoch1", f"{o}/r1/epoch2", f"{o}/r2/epoch1", f"{o}/r2/epoch2"]},
              open(f"{o}/summary.json", "w"), indent=1)


if __name__ == "__main__":
    main()
