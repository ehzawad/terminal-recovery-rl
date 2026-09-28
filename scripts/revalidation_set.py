"""Tasks whose v4 validity outcome the v4.1 changes can alter (amendment A6), one id per line.

Selected: hidden tests containing 'skip'; contracts permitting 'type_changed'; a moved-input or other fault
target that is a dotfile; any task or fault family with a harness/verifier error; every invalid task.
Tasks whose hidden tests run or import code are skipped (they are excluded from all rows anyway).

Usage: python scripts/revalidation_set.py --validity data/validity/v4.jsonl > runs/revalidate_v41.txt
"""

import argparse
import json
import os
import sys

from termrl.tasks import load_task, tests_execute_code
from termrl.config import POOL



def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validity", required=True)
    args = ap.parse_args()
    ids = json.load(open("data/audit/endless_recommended_ids.json"))
    recs = {}
    for line in open(args.validity):
        r = json.loads(line)
        recs[r["task_id"]] = r
    reasons = {}
    for tid in ids:
        task = load_task(os.path.join(POOL, tid))
        if tests_execute_code(task):
            continue
        r = recs.get(tid)
        why = []
        if r is None:
            why.append("not validated")
        else:
            if not r.get("valid"):
                why.append("invalid")
            if r.get("harness_error"):
                why.append("harness error")
            if "skip" in open(os.path.join(task.tests_dir, "test_final_state.py")).read():
                why.append("skip in tests")
            if any("type_changed" in k for k in (r.get("permitted") or {}).values()):
                why.append("type_changed permitted")
            for fam, e in (r.get("faults") or {}).items():
                if e.get("target") and os.path.basename(e["target"]).startswith("."):
                    why.append(f"dotfile target ({fam})")
                for ep in ("bite", "repaired"):
                    if (e.get(ep) or {}).get("error"):
                        why.append(f"{fam} {ep} error")
        if why:
            reasons[tid] = why
    for tid in reasons:
        print(tid)
    print(json.dumps({"count": len(reasons), "reasons": reasons}), file=sys.stderr)


if __name__ == "__main__":
    main()
