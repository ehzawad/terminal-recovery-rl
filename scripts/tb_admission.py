"""Model-free runtime admission of Terminal-Bench-style tasks in the offline sandbox (no policy model involved).

Per task: static flags (grader installs or downloads at grading time, instruction asks for downloads/installs,
reference solution downloads/installs); image build (network allowed at build time only); then, offline, a
no-op episode graded by the task's own grader, and two reference episodes (solution/solve.sh run in the task
shell, as root in WORKDIR, within the task's agent timeout) each graded the same way. Runtime pass = image
builds, the no-op scores below full credit, and both reference runs score full credit.

Usage: python scripts/tb_admission.py --pool ../.pools/tblite --out data/tb/admission_runtime.jsonl [--only a,b] [--workers 4]
"""

import argparse
import base64
import concurrent.futures as cf
import glob
import json
import os
import re
import threading
import time
import traceback

from termrl.tb import TBSandbox, grade, load_tb_task

NET = r"curl |wget |pip install|pip3 install|uvx|uv pip|apt-get install|apt install|git clone|npm install|https?://"


def static_flags(root: str) -> dict:
    read = lambda p: open(os.path.join(root, p)).read() if os.path.exists(os.path.join(root, p)) else ""
    return {"grader_installs": bool(re.search(r"curl|pip install|uvx|uv pip|apt-get", read("tests/test.sh"))),
            "instruction_mentions_network": bool(re.search(NET, read("instruction.md"))),
            "solution_uses_network": bool(re.search(NET, read("solution/solve.sh")))}


def episode(task, script: str | None, timeout: float) -> dict:
    sb = TBSandbox(task)
    try:
        ran = None
        if script:
            b64 = base64.b64encode(script.encode()).decode()
            r = sb.run(f"printf %s {b64} | base64 -d > /tmp/.ref.sh && bash /tmp/.ref.sh; rc=$?; rm -f /tmp/.ref.sh; (exit $rc)",
                       timeout=timeout)
            ran = {"exit_code": r.exit_code, "timed_out": r.timed_out, "seconds": round(r.seconds, 1), "tail": r.output[-600:]}
        v = grade(sb, task)
        return {"run": ran, "reward": v.reward, "success": v.success, "pytest_rc": v.pytest_rc, "error": v.error,
                "grade_seconds": v.seconds, "grader_tail": v.log_tail[-800:]}
    finally:
        sb.close()


def admit(root: str) -> dict:
    t0 = time.time()
    rec = {"task": os.path.basename(root.rstrip("/")), **static_flags(root)}
    try:
        task = load_tb_task(root)
        rec.update(workdir=task.workdir, service=task.service, cpus=task.cpus, memory_mb=task.memory_mb,
                   agent_timeout=task.agent_timeout, env_hash=task.env_hash())
        tb = time.time()
        task.ensure_image()
        rec["build_seconds"] = round(time.time() - tb, 1)
        rec["noop"] = episode(task, None, 60)
        solution = open(os.path.join(root, "solution", "solve.sh")).read()
        limit = min(task.agent_timeout, 1800)
        rec["reference"] = [episode(task, solution, limit) for _ in range(2)]
        rec["runtime_pass"] = (not rec["noop"]["success"]) and all(r["success"] for r in rec["reference"])
    except Exception:
        rec["runtime_pass"] = False
        rec["harness_error"] = traceback.format_exc()[-1500:]
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    roots = sorted(d.rstrip("/") for d in glob.glob(os.path.join(args.pool, "*/")) if os.path.exists(os.path.join(d, "task.toml")))
    if args.only:
        keep = set(args.only.split(","))
        roots = [r for r in roots if os.path.basename(r) in keep]
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    done = {json.loads(l)["task"] for l in open(args.out)} if os.path.exists(args.out) else set()
    todo = [r for r in roots if os.path.basename(r) not in done]
    lock, n = threading.Lock(), [len(done)]

    def work(root):
        rec = admit(root)
        with lock:
            with open(args.out, "a") as f:
                f.write(json.dumps(rec) + "\n")
            n[0] += 1
            ref = [r.get("reward") for r in rec.get("reference", [])]
            print(f"[{n[0]}/{len(roots)}] {rec['task']} pass={rec['runtime_pass']} noop={rec.get('noop', {}).get('reward')} "
                  f"ref={ref} build={rec.get('build_seconds')}s {rec['seconds']}s"
                  + (" HARNESS_ERROR" if rec.get("harness_error") else ""), flush=True)

    with cf.ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(work, todo))


if __name__ == "__main__":
    main()
