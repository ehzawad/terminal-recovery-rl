"""Arm D: SFT from the instruct weights on every verified safe success R collected (A1, A2, A5).

Reads R's rollout log (scripts/train_grpo.py writes one record per trajectory, exactly as generated),
keeps complete, non-truncated, harness-error-free successes with no collateral modification, reports
every record it drops and why, and fits with the same recipe as S under the registered two-hour limit.
Candidates for dev_monitor selection: epoch1 and epoch2.

Usage: python scripts/run_arm_d.py --rollouts runs/R_seed1/rollouts.jsonl [--out runs/D_seed1]
"""

import argparse
import collections
import json
import os
import subprocess
import sys

PY = sys.executable


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rollouts", required=True)
    ap.add_argument("--out", default="runs/D_seed1")
    ap.add_argument("--max-hours", type=float, default=2.0)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    kept, dropped, seen = [], collections.Counter(), set()
    for line in open(args.rollouts):
        r = json.loads(line)
        if r.get("attempt_id") in seen:
            dropped["duplicate attempt (resumed run)"] += 1
            continue
        seen.add(r.get("attempt_id"))
        v = r.get("verdict") or {}
        why = ("harness error" if r.get("harness_error") else "truncated" if r.get("truncated")
               else "collateral modification" if r.get("collateral") is not None
               else "not a complete success" if not v.get("success") else None)
        if why:
            dropped[why] += 1
        else:
            kept.append(r)
    data = os.path.join(args.out, "d_data.jsonl")
    with open(data, "w") as f:
        f.writelines(json.dumps(r) + "\n" for r in kept)
    ledger = {"rollouts": args.rollouts, "kept": len(kept), "dropped": dict(dropped)}
    print(json.dumps(ledger, indent=1), flush=True)
    subprocess.run([PY, "scripts/train_sft.py", "--data", data, "--out", args.out, "--max-hours", str(args.max_hours)],
                   check=True)
    ledger["candidates"] = [p for p in (f"{args.out}/epoch1", f"{args.out}/epoch2") if os.path.isdir(p)]
    json.dump(ledger, open(os.path.join(args.out, "summary.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
