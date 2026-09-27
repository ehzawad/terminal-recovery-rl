"""Build episode rows (one JSON line per episode) from the validity gate and the frozen split.

A row is {task_id, task_root, partition, fault_family, fault_seed, trial}. Every row carries the
task's planted fixtures (from its v3 contract). For faulted rows the family is drawn per
(task, trial) from that task's *usable* training families, so every arm sees exactly the same
episodes. `--families heldout` uses blocking_fifo; `--families clean` emits unfaulted rows;
`--families mix --fault-share F` faults a hash-chosen share F of (task, trial) episodes (on tasks
with a usable family) and leaves the rest clean.

Usage:
  python scripts/make_rows.py --partition dev_search --trials 2 --families train --out data/rows/dev_search_train.jsonl
"""

import argparse
import hashlib
import json
import os

from termrl import faults

POOL = "/mnt/sdb/arafat/ehz/llm/.pools/endless-terminals"


def usable_families(rec: dict, families: tuple[str, ...]) -> list[str]:
    return [f for f in families if rec.get("faults", {}).get(f, {}).get("usable")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--partition", required=True, nargs="+")
    ap.add_argument("--trials", type=int, default=4)
    ap.add_argument("--families", choices=["train", "heldout", "clean", "mix"], default="train")
    ap.add_argument("--fault-share", type=float, default=0.5)
    ap.add_argument("--validity", default="data/validity/v3.jsonl")
    ap.add_argument("--split", default="data/splits_v1.json")
    ap.add_argument("--limit", type=int, help="first N eligible tasks in sha256 order (deterministic subsample)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    split = json.load(open(args.split))["assignments"]
    validity = {}
    for line in open(args.validity):
        r = json.loads(line)
        validity[r["task_id"]] = r
    fams = {"train": faults.TRAIN_FAMILIES, "heldout": faults.HELDOUT_FAMILIES, "clean": (),
            "mix": faults.TRAIN_FAMILIES}[args.families]

    eligible = []
    for tid, rec in validity.items():
        if split.get(tid) not in args.partition or not rec.get("valid"):
            continue
        usable = usable_families(rec, fams)
        if args.families in ("clean", "mix") or usable:
            eligible.append((hashlib.sha256(f"rows:{tid}".encode()).hexdigest(), tid, usable))
    eligible.sort()
    if args.limit:
        eligible = eligible[: args.limit]

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    n = 0
    with open(args.out, "w") as f:
        for _, tid, usable in eligible:
            for k in range(args.trials):
                fault_this = bool(usable) and args.families != "clean"
                if args.families == "mix":
                    u = int(hashlib.sha256(f"mix:{tid}:{k}".encode()).hexdigest()[:8], 16) / 16**8
                    fault_this = fault_this and u < args.fault_share
                fam = None
                if fault_this:
                    fam = usable[int(hashlib.sha256(f"family:{tid}:{k}".encode()).hexdigest()[:8], 16) % len(usable)]
                f.write(json.dumps({"task_id": tid, "task_root": os.path.join(POOL, tid), "partition": split[tid],
                                    "fault_family": fam, "fault_seed": k, "trial": k}) + "\n")
                n += 1
    print(f"{len(eligible)} tasks, {n} rows -> {args.out}")


if __name__ == "__main__":
    main()
