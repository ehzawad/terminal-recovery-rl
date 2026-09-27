"""Build the one authoritative contract file from finished validity records (amendment A6).

Later records override earlier ones for the same task. A contract is written only for a valid task,
with its test inventory, the usable fault targets, and the identities it was validated against (task
environment hash, sha256 of the hidden tests, harness version). The file is written atomically; the
environment reads only this frozen file.

Usage: python scripts/freeze_contracts.py --validity data/validity/v4.jsonl [--validity more.jsonl] \
           --out data/contracts_v4_frozen.jsonl
"""

import argparse
import hashlib
import json
import os

POOL = "/mnt/sdb/arafat/ehz/llm/.pools/endless-terminals"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validity", action="append", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    recs = {}
    for path in args.validity:
        for line in open(path):
            r = json.loads(line)
            recs[r["task_id"]] = r
    tmp = args.out + ".tmp"
    n = 0
    with open(tmp, "w") as f:
        for tid, r in sorted(recs.items()):
            if not r.get("valid") or not r.get("tests"):
                continue
            tests_sha = hashlib.sha256(open(f"{POOL}/{tid}/tests/test_final_state.py", "rb").read()).hexdigest()[:16]
            usable = {k: v["target"] for k, v in r.get("faults", {}).items() if v.get("usable")}
            f.write(json.dumps({"task_id": tid, "fixture_level": r["fixture_level"], "permitted": r["permitted"],
                                "tests": r["tests"], "fault_targets": usable, "env_hash": r["env_hash"],
                                "tests_sha": tests_sha, "harness": r.get("harness")}) + "\n")
            n += 1
    os.replace(tmp, args.out)
    print(f"{n} contracts -> {args.out} (from {len(recs)} validity records)")


if __name__ == "__main__":
    main()
