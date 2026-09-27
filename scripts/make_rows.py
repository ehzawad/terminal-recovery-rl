"""Build episode rows from the v4 validity gate and the frozen split (amendment A5).

A *configuration* is (task, fault family or clean, fault seed). Rows are configurations repeated
`--attempts` times with identical fault fields, so repeated attempts of one configuration form a
group exactly like a GRPO group. Every row has a unique `row_id` used for resuming and for pairing
arms; its sampling seed is derived from the row id.

Fault state per configuration:
  --families train     every configuration faulted with one of the task's usable training families
  --families heldout   every configuration faulted with blocking_fifo
  --families clean     no fault
  --families mix       a hash-chosen share `--fault-share` of configurations *on faultable tasks* is
                       faulted (tasks without a usable family are always clean; the realised share is
                       printed)
Eligibility: `--require-faultable` keeps only tasks with a usable training family (A1 for P selection).
The family is drawn per configuration from the task's usable families; the target is fixed by the
contract. `--configs-per-task K` makes K configurations per task (config index c = 0..K-1, fault
seed c); `--limit` keeps the first N configurations in sha256 order.

Usage:
  python scripts/make_rows.py --partition train --families mix --fault-share 0.25 --limit 256 \
      --attempts 1 --out data/rows/train_configs.jsonl
"""

import argparse
import hashlib
import json
import os

from termrl import faults

POOL = "/mnt/sdb/arafat/ehz/llm/.pools/endless-terminals"


def h(*parts) -> int:
    return int(hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()[:12], 16)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--partition", required=True, nargs="+")
    ap.add_argument("--families", choices=["train", "heldout", "clean", "mix"], required=True)
    ap.add_argument("--fault-share", type=float, default=0.5)
    ap.add_argument("--require-faultable", action="store_true")
    ap.add_argument("--configs-per-task", type=int, default=1)
    ap.add_argument("--attempts", type=int, default=1)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--skip", type=int, default=0, help="drop the first N configurations (after ordering)")
    ap.add_argument("--validity", default="data/validity/v4.jsonl")
    ap.add_argument("--split", default="data/splits_v1.json")
    ap.add_argument("--salt", default="rows-v4")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    split = json.load(open(args.split))["assignments"]
    validity = {}
    for line in open(args.validity):
        r = json.loads(line)
        validity[r["task_id"]] = r
    fams = {"train": faults.TRAIN_FAMILIES, "heldout": faults.HELDOUT_FAMILIES, "clean": (),
            "mix": faults.TRAIN_FAMILIES}[args.families]

    configs = []
    for tid, rec in validity.items():
        if split.get(tid) not in args.partition or not rec.get("valid"):
            continue
        usable = [f for f in fams if rec.get("faults", {}).get(f, {}).get("usable")]
        train_usable = [f for f in faults.TRAIN_FAMILIES if rec.get("faults", {}).get(f, {}).get("usable")]
        if args.require_faultable and not train_usable:
            continue
        if args.families in ("train", "heldout") and not usable:
            continue
        for c in range(args.configs_per_task):
            fam = None
            if usable and args.families != "clean":
                faulted = True
                if args.families == "mix":
                    faulted = (h(args.salt, "mix", tid, c) % 10**6) / 10**6 < args.fault_share
                if faulted:
                    fam = usable[h(args.salt, "family", tid, c) % len(usable)]
            configs.append((h(args.salt, "order", tid, c), tid, c, fam))
    configs.sort()
    configs = configs[args.skip:]
    if args.limit:
        configs = configs[: args.limit]

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    n_faulted = sum(1 for *_, fam in configs if fam)
    with open(args.out, "w") as f:
        for _, tid, c, fam in configs:
            for a in range(args.attempts):
                f.write(json.dumps({"row_id": f"{tid}:c{c}:a{a}", "task_id": tid, "task_root": os.path.join(POOL, tid),
                                    "partition": split[tid], "fault_family": fam, "fault_seed": c, "config": c,
                                    "attempt": a, "trial": a}) + "\n")
    print(f"{len(configs)} configurations ({n_faulted} faulted, {len(configs) - n_faulted} clean) x "
          f"{args.attempts} attempts = {len(configs) * args.attempts} rows -> {args.out}")


if __name__ == "__main__":
    main()
