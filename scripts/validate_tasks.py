"""Validity gate for tasks and (task, fault) pairs, under the exact agent harness.

Per task, with the agent's non-root shell and home ownership:
  noop      nothing is done              -> must fail (else the task is already solved)
  reference solution/solve.sh is run     -> must pass (else the task or verifier is broken)
Per fault family with an eligible target:
  bite      fault injected, reference run without repair -> should fail (else the fault is inert)
  repaired  fault injected, generic repair then reference -> must pass (a correct recovery exists)

Writes one JSON line per task. Usage:
  python scripts/validate_tasks.py --ids data/audit/endless_recommended_ids.json --out data/validity/v1.jsonl
"""

import argparse
import base64
import concurrent.futures as cf
import json
import os
import threading
import time
import traceback

from termrl import faults
from termrl.sandbox import Sandbox, docker
from termrl.tasks import load_task
from termrl.verify import verify_image

POOL = "/mnt/sdb/arafat/ehz/llm/.pools/endless-terminals"


def script_cmd(script: str) -> str:
    b64 = base64.b64encode(script.encode()).decode()
    return f"printf %s {b64} | base64 -d > /tmp/.ref.sh && bash /tmp/.ref.sh; rc=$?; rm -f /tmp/.ref.sh; (exit $rc)"


def trial(task, prelude: str | None = None, fault: str | None = None, seed: int = 0, run_reference: bool = True,
          run_timeout: float = 180) -> dict:
    with Sandbox(task.image) as sb:
        applied = None
        if fault:
            f = faults.choose(task, fault, seed)
            applied = faults.inject(sb, f, seed)
        script = ""
        if prelude is not None:
            script += (faults.repair_script(applied) if prelude == "repair" else prelude) + "\n"
        if run_reference:
            script += task.solution
        out = sb.run(script_cmd(script), timeout=run_timeout) if script.strip() else None
        snap = sb.commit()
    try:
        v = verify_image(snap, task.tests_dir)
    finally:
        docker(["rmi", "-f", snap], check=False, timeout=120)
    return {"passed": v.passed, "total": v.total, "success": v.success, "error": v.error,
            "exit": None if out is None else out.exit_code, "fault": applied.as_dict() if applied else None}


def validate(task_id: str) -> dict:
    t0 = time.time()
    task = load_task(os.path.join(POOL, task_id))
    rec = {"task_id": task_id, "env_hash": task.env_hash()}
    try:
        task.ensure_image()
        rec["noop"] = trial(task, run_reference=False)
        rec["reference"] = trial(task)
        rec["valid"] = (not rec["noop"]["success"]) and rec["reference"]["success"] and not rec["noop"]["error"]
        rec["faults"] = {}
        if rec["valid"]:
            for fam in faults.TRAIN_FAMILIES + faults.HELDOUT_FAMILIES:
                if faults.choose(task, fam, 0) is None:
                    rec["faults"][fam] = {"eligible": False}
                    continue
                bite = trial(task, fault=fam, run_timeout=45)  # a blocked reference is the expected outcome
                entry = {"eligible": True, "bite": bite}
                if fam != "missing_tool":
                    entry["repaired"] = trial(task, prelude="repair", fault=fam)
                    entry["usable"] = (not bite["success"]) and entry["repaired"]["success"]
                else:
                    entry["usable"] = not bite["success"]
                rec["faults"][fam] = entry
    except Exception:
        rec["valid"] = False
        rec["harness_error"] = traceback.format_exc()[-2000:]
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True, help="JSON list of task ids, or a text file with one id/path per line")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    if args.ids.endswith(".json"):
        ids = json.load(open(args.ids))
    else:
        ids = [l.strip().split("/")[-1] for l in open(args.ids) if l.strip() and not l.startswith("#")]
    if args.limit:
        ids = ids[: args.limit]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    done = {json.loads(l)["task_id"] for l in open(args.out)} if os.path.exists(args.out) else set()
    todo = [i for i in ids if i not in done]
    lock = threading.Lock()
    n = [len(done)]

    def work(i):
        rec = validate(i)
        with lock:
            with open(args.out, "a") as f:
                f.write(json.dumps(rec) + "\n")
            n[0] += 1
            fam = {k: ("-" if not v.get("eligible") else ("U" if v.get("usable") else "x")) for k, v in rec.get("faults", {}).items()}
            print(f"[{n[0]}/{len(ids)}] {i} valid={rec['valid']} faults={fam} {rec['seconds']}s"
                  + (" HARNESS_ERROR" if rec.get("harness_error") else ""), flush=True)

    with cf.ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(work, todo))


if __name__ == "__main__":
    main()
