"""Validity gate and contract builder for harness v3 (pre-registration amendment A2).

Per task, trying fixture placements 'full' then 'sibling':
  noop       nothing is done                         -> must fail
  reference  solution/solve.sh as the agent's uid    -> must pass, must not touch a planted fixture
The objects the reference modifies become the task's permitted write set (the contract). Then the
oracle is self-tested: reference + deleting one planted fixture must be flagged as collateral,
reference alone must not be. Per fault family with an eligible target:
  bite       fault, reference without repair         -> should fail (else the fault is inert)
  repaired   fault, generic repair, reference        -> must pass with no collateral modification
Writes one JSON line per task; contracts for valid tasks go to --contracts as well.

Usage:
  python scripts/validate_tasks.py --ids data/validity/v1_order.txt --out data/validity/v3.jsonl \
      --contracts data/contracts_v3.jsonl --workers 8
"""

import argparse
import base64
import concurrent.futures as cf
import json
import os
import shlex
import threading
import time
import traceback

from termrl import faults, manifest
from termrl.env import TerminalEnv
from termrl.tasks import load_task

POOL = "/mnt/sdb/arafat/ehz/llm/.pools/endless-terminals"


def script_cmd(script: str) -> str:
    b64 = base64.b64encode(script.encode()).decode()
    return f"printf %s {b64} | base64 -d > /tmp/.ref.sh && bash /tmp/.ref.sh; rc=$?; rm -f /tmp/.ref.sh; (exit $rc)"


def episode(root, *, level, contract=None, fault=None, script=None, repair=False, run_timeout=180,
            measure_writes=False):
    env = TerminalEnv(command_timeout=run_timeout)
    env.reset(task_root=root, fault_family=fault, fault_seed=0, fixture_level=level, contract=contract or {})
    writes = None
    try:
        if script:
            if repair:
                script = faults.repair_script(env._fault) + "\n" + script
            out = env._sandbox.run(script_cmd(script), timeout=run_timeout)
            if measure_writes:
                writes = sorted(e["path"] for e in manifest.diff(env._baseline, manifest.take(env._sandbox.name), set()))
            env._check_collateral()
            if fault and not repair and out.timed_out:
                # The reference itself hung on the fault: it bites by construction, no need to grade.
                return {"success": False, "timed_out": True, "fault": env._fault.as_dict()}, writes
        v = env._finish()
    finally:
        env._teardown()
    return {"passed": v.passed, "total": v.total, "success": v.success, "error": v.error,
            "collateral": env._collateral, "fabricated_input": env._fabricated_input,
            "fault_cleared": env._fault_cleared, "fixtures": [p for p, _ in env._fixtures],
            "fault": env._fault.as_dict() if env._fault else None}, writes


def validate(task_id: str) -> dict:
    t0 = time.time()
    root = os.path.join(POOL, task_id)
    task = load_task(root)
    rec = {"task_id": task_id, "env_hash": task.env_hash(), "valid": False, "attempts": []}
    try:
        _validate_into(task, root, rec)
    except Exception:
        rec["valid"] = False
        rec["harness_error"] = traceback.format_exc()[-2000:]
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


def _validate_into(task, root: str, rec: dict) -> None:
    task.ensure_image()
    for level in ("full", "sibling"):
        noop, _ = episode(root, level=level)
        ref, writes = episode(root, level=level, script=task.solution, measure_writes=True)
        touched_fixture = sorted(set(ref["fixtures"]) & set(writes or []))
        ok = (not noop["success"]) and ref["success"] and not touched_fixture and not noop["error"]
        rec["attempts"].append({"level": level, "noop": noop, "reference": ref, "writes": writes,
                                "touched_fixture": touched_fixture, "ok": ok})
        if ok:
            rec.update(valid=True, fixture_level=level, permitted=writes, fixtures=ref["fixtures"])
            break
    if not rec["valid"]:
        return
    contract = {"fixture_level": rec["fixture_level"], "permitted": rec["permitted"]}
    victim = rec["fixtures"][0]
    damaged, _ = episode(root, level=rec["fixture_level"], contract=contract,
                         script=task.solution + f"\nrm -f {shlex.quote(victim)}\n")
    clean, _ = episode(root, level=rec["fixture_level"], contract=contract, script=task.solution)
    rec["oracle_selftest"] = {"damage_detected": damaged["collateral"] is not None,
                              "reference_clean": clean["collateral"] is None and clean["success"]}
    rec["valid"] = rec["oracle_selftest"]["damage_detected"] and rec["oracle_selftest"]["reference_clean"]
    rec["faults"] = {}
    if rec["valid"]:
        for fam in faults.TRAIN_FAMILIES + faults.HELDOUT_FAMILIES:
            if faults.choose(task, fam, 0) is None:
                rec["faults"][fam] = {"eligible": False}
                continue
            bite, _ = episode(root, level=rec["fixture_level"], contract=contract, fault=fam,
                              script=task.solution, run_timeout=25)
            entry = {"eligible": True, "bite": bite}
            if fam != "missing_tool":
                rep, _ = episode(root, level=rec["fixture_level"], contract=contract, fault=fam,
                                 script=task.solution, repair=True)
                entry["repaired"] = rep
                entry["usable"] = (not bite["success"]) and rep["success"] and rep["collateral"] is None
            else:
                entry["usable"] = not bite["success"]
            rec["faults"][fam] = entry


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True, help="JSON list of task ids, or a text file with one id/path per line")
    ap.add_argument("--out", required=True)
    ap.add_argument("--contracts", required=True)
    ap.add_argument("--workers", type=int, default=6)
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
            if rec["valid"]:
                with open(args.contracts, "a") as f:
                    f.write(json.dumps({"task_id": i, "fixture_level": rec["fixture_level"],
                                        "permitted": rec["permitted"]}) + "\n")
            n[0] += 1
            fam = {k: ("-" if not v.get("eligible") else ("U" if v.get("usable") else "x"))
                   for k, v in rec.get("faults", {}).items()}
            print(f"[{n[0]}/{len(ids)}] {i} valid={rec['valid']} level={rec.get('fixture_level')} "
                  f"selftest={rec.get('oracle_selftest')} faults={fam} {rec['seconds']}s"
                  + (" HARNESS_ERROR" if rec.get("harness_error") else ""), flush=True)

    with cf.ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(work, todo))


if __name__ == "__main__":
    main()
