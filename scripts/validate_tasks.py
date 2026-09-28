"""Validity gate and contract builder for harness v4 (pre-registration amendment A5).

Per task, trying fixture placements 'full' then 'sibling':
  noop        nothing is done                                      -> must fail
  reference   solution/solve.sh as the agent's uid, run twice      -> must pass both times, touch no
              planted fixture, and change the same objects in the same ways both times
The contract records, per object, which properties the reference changes (a mode-only change does
not license a content change), and the expected hidden-test inventory. Oracle self-test with the
contract: reference + deleting a planted fixture must be flagged; reference alone must be clean.
Per fault family (perm_denied, moved_input; blocking_fifo held out), with the target chosen among
inputs the task never edits and fixed per (task, family):
  bite        fault, reference without repair                     -> must fail (or hang)
  repaired    fault, generic repair, reference                    -> must pass, no collateral,
              fault cleared byte-for-byte
  forged      fault, then the input path overwritten with other bytes -> must be flagged
With --clean-only the fault families are skipped. With --discrimination (A8, A8.1) the graded outputs (regular
files the reference created or changed whose path or name appears in the hidden tests) are mutated one at a
time after a reference run and graded from their own snapshot: m1 emptied, m2 last line removed, m3 first
digit changed, m4 first line duplicated. Pass: for every graded output, m1 fails and at least one applicable
of m2/m3 fails (m4 is reported only).
Usage:
  python scripts/validate_tasks.py --ids data/validity/v1_order.txt --out data/validity/v4.jsonl \
      --contracts data/contracts_v4.jsonl --workers 8
"""

import argparse
import base64
import collections
import concurrent.futures as cf
import json
import os
import shlex
import threading
import time
import traceback

from termrl import faults, manifest
from termrl.env import TerminalEnv
from termrl.sandbox import docker
from termrl.tasks import load_task
from termrl.verify import verify_image
from termrl.config import POOL

FAMILIES = faults.TRAIN_FAMILIES + faults.HELDOUT_FAMILIES
OPTIONS = {"clean_only": False, "discrimination": False}

MUTATE = r"""
import sys
p, m = sys.argv[1], sys.argv[2]
b = open(p, "rb").read()
lines = b.splitlines(keepends=True)
if m == "m1":
    out = b""
elif m == "m2":
    out = b"".join(lines[:-1])
elif m == "m3":
    i = next((k for k, c in enumerate(b) if 48 <= c <= 57), None)
    if i is None:
        sys.exit(3)
    out = b[:i] + bytes([48 + (b[i] - 47) % 10]) + b[i + 1:]
else:
    if not lines:
        sys.exit(3)
    out = lines[0] + b
if out == b:
    sys.exit(3)
with open(p, "r+b") as f:
    f.seek(0)
    f.write(out)
    f.truncate()
"""


def script_cmd(script: str) -> str:
    b64 = base64.b64encode(script.encode()).decode()
    return f"printf %s {b64} | base64 -d > /tmp/.ref.sh && bash /tmp/.ref.sh; rc=$?; rm -f /tmp/.ref.sh; (exit $rc)"


def episode(root, *, contract, fault=None, script=None, repair=False, run_timeout=180, measure_writes=False):
    env = TerminalEnv(command_timeout=run_timeout)
    env.reset(task_root=root, fault_family=fault, fault_seed=0, contract={**contract, "provisional": True})
    if env._broken:
        raise RuntimeError(env._broken)
    writes = None
    try:
        if script:
            if repair:
                script = faults.repair_script(env._fault) + "\n" + script
            out = env._sandbox.run(script_cmd(script), timeout=run_timeout)
            if measure_writes:
                ev = manifest.diff(env._baseline, manifest.take(env._sandbox.name), {})
                w = collections.defaultdict(set)
                for e in ev:
                    w[e["path"]].add(e["kind"])
                writes = {p: sorted(k) for p, k in sorted(w.items())}
            env._check_collateral()
            if fault and not repair and out.timed_out:
                return {"success": False, "timed_out": True, "error": None, "fault": env._fault.as_dict(),
                        "collateral": env._collateral}, writes
        res = env._result()
        v = env._verdict
    finally:
        env._teardown()
    return {"passed": v.passed, "total": v.total, "success": v.success, "error": res["error"], "tests": v.tests,
            "collateral": env._collateral, "fabricated_input": env._fabricated_input,
            "fault_cleared": env._fault_cleared, "fixtures": [p for p, _ in env._fixtures],
            "fault": env._fault.as_dict() if env._fault else None}, writes


def discrimination(task, root: str, contract: dict) -> dict:
    """Mutate each graded output of one reference run and grade every mutant from its own snapshot."""
    tests_text = open(os.path.join(task.tests_dir, "test_final_state.py")).read()
    env = TerminalEnv(command_timeout=180)
    env.reset(task_root=root, contract={**contract, "provisional": True})
    if env._broken:
        raise RuntimeError(env._broken)
    sb = env._sandbox
    out = {"targets": {}, "reference_passes": None}
    snaps = []
    try:
        sb.run(script_cmd(task.solution), timeout=180)
        docker(["exec", "-u", "0:0", sb.name, "sh", "-c", "kill -9 -1"], check=False, timeout=30)
        now, base = manifest.take(sb.name), env._baseline
        changed = [p for p, v in sorted(now.items()) if v[0] == "f"
                   and (p not in base or base[p][0] != "f" or base[p][4] != v[4])]
        graded = [p for p in changed if p in tests_text or os.path.basename(p) in tests_text]

        def grade() -> bool:
            snap = sb.commit()
            snaps.append(snap)
            v = verify_image(snap, task.tests_dir, expected_tests=contract["tests"])
            docker(["rmi", "-f", snap], check=False, timeout=120)
            return bool(v.success)

        out["reference_passes"] = grade()
        for i, p in enumerate(graded):
            q = shlex.quote(p)
            sb.root_exec(f"cp -p {q} /tmp/.orig{i}")
            res = {}
            for m in ("m1", "m2", "m3", "m4"):
                r = docker(["exec", "-u", "0:0", sb.name, "python3", "-c", MUTATE, p, m], check=False, timeout=60)
                if r.returncode == 3:
                    res[m] = "n/a"
                    continue
                if r.returncode != 0:
                    res[m] = "mutation_error"
                    continue
                res[m] = "caught" if not grade() else "survived"
                sb.root_exec(f"cp -p /tmp/.orig{i} {q}")
            res["pass"] = res["m1"] == "caught" and any(res[m] == "caught" for m in ("m2", "m3")) \
                if any(res[m] in ("caught", "survived") for m in ("m2", "m3")) else res["m1"] == "caught"
            out["targets"][p] = res
        out["changed_files"] = len(changed)
        out["pass"] = bool(out["reference_passes"]) and all(t["pass"] for t in out["targets"].values())
    finally:
        env._teardown()
    return out


def validate(task_id: str) -> dict:
    t0 = time.time()
    root = os.path.join(POOL, task_id)
    task = load_task(root)
    rec = {"task_id": task_id, "env_hash": task.env_hash(), "harness": "v4.1", "valid": False, "attempts": []}
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
        bare = {"fixture_level": level, "permitted": {}}
        noop, _ = episode(root, contract=bare)
        ref1, w1 = episode(root, contract=bare, script=task.solution, measure_writes=True)
        ref2, w2 = episode(root, contract=bare, script=task.solution, measure_writes=True)
        touched_fixture = sorted(set(ref1["fixtures"]) & set(w1 or {}))
        ok = (not noop["success"] and not noop["error"] and ref1["success"] and ref2["success"]
              and w1 == w2 and ref1["tests"] == ref2["tests"] and not touched_fixture)
        rec["attempts"].append({"level": level, "noop": noop, "reference": [ref1, ref2], "writes": [w1, w2],
                                "touched_fixture": touched_fixture, "ok": ok})
        if ok:
            rec.update(valid=True, fixture_level=level, permitted=w1, tests=ref1["tests"], fixtures=ref1["fixtures"])
            break
    if not rec["valid"]:
        return
    contract = {"fixture_level": rec["fixture_level"], "permitted": rec["permitted"], "tests": rec["tests"]}
    victim = rec["fixtures"][0]
    damaged, _ = episode(root, contract=contract, script=task.solution + f"\nrm -f {shlex.quote(victim)}\n")
    clean, _ = episode(root, contract=contract, script=task.solution)
    rec["oracle_selftest"] = {"damage_detected": damaged["collateral"] is not None,
                              "reference_clean": clean["collateral"] is None and clean["success"]}
    rec["valid"] = rec["oracle_selftest"]["damage_detected"] and rec["oracle_selftest"]["reference_clean"]
    rec["faults"] = {}
    if not rec["valid"]:
        return
    if OPTIONS["discrimination"]:
        rec["discrimination"] = discrimination(task, root, contract)
    if OPTIONS["clean_only"]:
        return
    exclude = set(rec["permitted"])
    for fam in FAMILIES:
        f = faults.choose(task, fam, 0, exclude=exclude)
        if f is None:
            rec["faults"][fam] = {"eligible": False}
            continue
        c = {**contract, "fault_targets": {fam: f.target}}
        try:  # a problem with one fault family never invalidates the task itself
            bite, _ = episode(root, contract=c, fault=fam, script=task.solution, run_timeout=25)
            rep, _ = episode(root, contract=c, fault=fam, script=task.solution, repair=True)
            forged, _ = episode(root, contract=c, fault=fam,
                                script=f"rm -f {shlex.quote(f.target)}; echo forged > {shlex.quote(f.target)}")
        except Exception:
            rec["faults"][fam] = {"eligible": True, "target": f.target, "usable": False,
                                  "error": traceback.format_exc()[-800:]}
            continue
        entry = {"eligible": True, "target": f.target, "bite": bite, "repaired": rep,
                 "forgery_detected": forged["collateral"] is not None}
        genuine_bite = (not bite["success"]) and (bite.get("timed_out") or not bite.get("error"))
        entry["usable"] = (genuine_bite and rep["success"] and not rep.get("error") and rep["collateral"] is None
                           and bool(rep["fault_cleared"]) and entry["forgery_detected"])
        rec["faults"][fam] = entry


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True, help="JSON list of task ids, or a text file with one id/path per line")
    ap.add_argument("--out", required=True)
    ap.add_argument("--contracts", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--clean-only", action="store_true", help="skip the fault families")
    ap.add_argument("--discrimination", action="store_true", help="mutate graded outputs (A8)")
    args = ap.parse_args()
    OPTIONS.update(clean_only=args.clean_only, discrimination=args.discrimination)
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
                usable = {k: v["target"] for k, v in rec["faults"].items() if v.get("usable")}
                with open(args.contracts, "a") as f:
                    f.write(json.dumps({"task_id": i, "fixture_level": rec["fixture_level"], "permitted": rec["permitted"],
                                        "tests": rec["tests"], "fault_targets": usable}) + "\n")
            n[0] += 1
            fam = {k: ("-" if not v.get("eligible") else ("U" if v.get("usable") else "x"))
                   for k, v in rec.get("faults", {}).items()}
            disc = rec.get("discrimination") or {}
            print(f"[{n[0]}/{len(ids)}] {i} valid={rec['valid']} level={rec.get('fixture_level')} "
                  f"selftest={rec.get('oracle_selftest')} faults={fam} "
                  f"disc={disc.get('pass')}/{len(disc.get('targets', {}))} {rec.get('seconds')}s"
                  + (" HARNESS_ERROR" if rec.get("harness_error") else ""), flush=True)

    with cf.ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(work, todo))


if __name__ == "__main__":
    main()
