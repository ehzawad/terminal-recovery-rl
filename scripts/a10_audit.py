"""A10 executable audit of the CLI-Gym sample.

Per task: build the damaged image (network on), then in fresh offline containers: no-op grade (must fail),
gold image graded twice (must pass), repair reference `refs/<key>.sh` twice (must pass), blind wrong-output
control `mutants/<key>.sh` once (must fail). Records go to results/A10/records/<key>.json.
Usage: a10_audit.py [--only KEY,..] [--jobs N] [--stage base|full] [--rm]
       a10_audit.py --try KEY FILE     (reference author: one counted attempt, max 3)
       a10_audit.py --explore KEY CMD  (run CMD in a fresh offline damaged container, not graded)
"""
from __future__ import annotations

import argparse, concurrent.futures as cf, hashlib, json, os, re, shlex, subprocess, sys, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import a9_audit as A9  # noqa: E402
from termrl.sandbox import docker  # noqa: E402

POOL = Path("/mnt/sdb/arafat/ehz/llm/.pools/audit10")
OUT = ROOT / "results/A10"
BUILD = POOL / "build"
MAX_TRIES = 3
TEST_TIMEOUT = 1500
PYTEST_CALL = re.compile(r"pytest --disable-warnings[^']*?--verbose ([^']+)'")
SUMMARY = re.compile(r"^=+ (.*(?:passed|failed|error|no tests ran).*) in [\d.]+s", re.M)
LINE = re.compile(r"^(\S+::\S+?)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b", re.M)


def rows() -> dict[str, dict]:
    return {r["key"]: r for r in json.load(open(OUT / "sample.json"))["tasks"]}


def task(r: dict) -> dict:
    d = pd.read_parquet(POOL / "train.parquet").set_index("task_id").loc[r["task_id"]]
    return {"task_yaml": d.task_yaml, "dockerfile": d.dockerfile, "run_tests": d.run_tests}


def spec_of(r: dict) -> dict:
    t = task(r)
    ctx = BUILD / r["key"]
    ctx.mkdir(parents=True, exist_ok=True)
    (ctx / "Dockerfile").write_text(t["dockerfile"])
    (ctx / "run_tests.sh").write_text(t["run_tests"])
    (ctx / "task.yaml").write_text(t["task_yaml"])
    m = PYTEST_CALL.search(t["run_tests"])
    ids = m.group(1).split() if m else []
    h = hashlib.sha256(t["dockerfile"].encode()).hexdigest()[:10]
    return {"key": r["key"], "ctx": str(ctx), "image": f"a10:{r['key'][8:60].lower()}-{h}", "gold": r["base"],
            "workdir": "/testbed", "run_tests": t["run_tests"], "test_ids": ids}


def build(spec: dict) -> tuple[bool, str]:
    return A9.build(spec)


class Box(A9.Box):
    """A9's offline box, pinned to 2 CPUs so the container also *sees* 2 (pytest -n auto sizes itself by it)."""

    def __init__(self, spec: dict):
        self.spec = spec
        self.name = "a10" + hashlib.sha256(os.urandom(16)).hexdigest()[:12]
        k = int(self.name[3:11], 16) % (os.cpu_count() // 2)
        docker(["run", "-d", "--name", self.name, "--network", "none", "--cpuset-cpus", f"{2*k},{2*k+1}", "--memory", "4g",
                "--memory-swap", "4g", "--pids-limit", "1024", "--cap-drop", "NET_RAW", "--workdir", spec["workdir"],
                "--entrypoint", "/bin/sh", spec["image"], "-c", "exec sleep infinity"], timeout=600)


def box(spec: dict, gold: bool = False) -> Box:
    return Box({**spec, "image": spec["gold"] if gold else spec["image"]})


def grade(b: A9.Box) -> dict:
    spec = b.spec
    t0 = time.time()
    rc, out = b.sh("cat > /tmp/.run_tests.sh <<'A10EOF'\n" + spec["run_tests"] + "\nA10EOF\ncd /testbed && bash /tmp/.run_tests.sh >/tmp/.rt.out 2>&1; "
                   "echo RC=$?; cat /test.log 2>/dev/null", TEST_TIMEOUT)
    norm = lambda s: s.replace("\\", "")
    seen = {norm(m.group(1)): m.group(2) for m in LINE.finditer(out or "")}
    status = {i: seen.get(norm(i), "MISSING") for i in spec["test_ids"]}
    tail = SUMMARY.findall(out or "")
    counts = dict((k, int(n)) for n, k in re.findall(r"(\d+) (passed|failed|error|errors|skipped)", tail[-1])) if tail else {}
    by_summary = (counts.get("passed", 0) > 0 if not status else counts.get("passed") == len(status)) and not any(counts.get(k) for k in ("failed", "error", "errors") + (("skipped",) if status else ()))
    by_ids = bool(status) and all(v == "PASSED" for v in status.values())
    ok = rc is not None and (by_ids or by_summary)
    return {"pass": ok, "rule": "ids" if by_ids else "summary" if by_summary else None, "summary": tail[-1] if tail else None,
            "n_ids": len(status), "n_pass": sum(v == "PASSED" for v in status.values()),
            "not_passed": {k: v for k, v in status.items() if v != "PASSED"}, "timeout": rc is None,
            "seconds": round(time.time() - t0, 1), "log_tail": (out or "")[-1500:]}


def run_script(spec: dict, script: str) -> dict:
    with box(spec) as b:
        rc, out = b.sh(script, 900)
        g = grade(b)
    return {"script_rc": rc, "script_tail": out[-1500:], "grade": g}


def audit(r: dict, stage: str, rm: bool) -> dict:
    spec = spec_of(r)
    path = OUT / "records" / f"{r['key']}.json"
    rec = json.loads(path.read_text()) if path.exists() else {"key": r["key"], "task_id": r["task_id"], "base": r["base"]}
    ok, msg = build(spec)
    rec["build"] = {"ok": ok, "msg": msg}
    if ok and "noop" not in rec:
        with box(spec) as b:
            rec["noop"] = grade(b)
        rec["gold"] = []
        for _ in range(2):
            with box(spec, gold=True) as b:
                rec["gold"].append(grade(b))
    if ok and stage == "full":
        ref = OUT / "refs" / f"{r['key']}.sh"
        rec["reference"] = [run_script(spec, ref.read_text()) for _ in range(2)] if ref.exists() else None
        mut = OUT / "mutants" / f"{r['key']}.sh"
        rec["mutant"] = run_script(spec, mut.read_text()) if mut.exists() else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=1))
    if rm:
        docker(["image", "rm", "-f", spec["image"], spec["gold"]], check=False, timeout=300)
    return rec


def summary_line(rec: dict) -> str:
    f = lambda g: "P" if g and g["pass"] else "F"
    ref = rec.get("reference")
    return (f"{rec['key'][:70]:70} build={'ok' if rec['build']['ok'] else 'FAIL'} "
            f"noop={f(rec.get('noop'))}({(rec.get('noop') or {}).get('n_pass')}/{(rec.get('noop') or {}).get('n_ids')}) "
            f"gold={''.join(f(g) for g in rec.get('gold', []))} ref={''.join(f(x['grade']) for x in ref) if ref else '-'} "
            f"mut={f(rec['mutant']['grade']) if rec.get('mutant') else '-'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--stage", choices=["base", "full"], default="base")
    ap.add_argument("--rm", action="store_true")
    ap.add_argument("--try", dest="try_", nargs=2, metavar=("KEY", "FILE"))
    ap.add_argument("--explore", nargs=2, metavar=("KEY", "CMD"))
    a = ap.parse_args()
    R = rows()
    if a.try_:
        key, f = a.try_
        d = OUT / "attempts" / key
        d.mkdir(parents=True, exist_ok=True)
        n = len(list(d.glob("*.json")))
        if n >= MAX_TRIES:
            sys.exit(f"attempt budget used ({MAX_TRIES}); no more tries for {key}")
        spec = spec_of(R[key])
        build(spec)
        res = run_script(spec, Path(f).read_text())
        (d / f"{n+1}.sh").write_text(Path(f).read_text())
        (d / f"{n+1}.json").write_text(json.dumps(res, indent=1))
        g = res["grade"]
        print(json.dumps({"attempt": n + 1, "of": MAX_TRIES, "pass": g["pass"], "n_pass": g["n_pass"], "n_ids": g["n_ids"],
                          "not_passed": dict(list(g["not_passed"].items())[:15]), "script_rc": res["script_rc"],
                          "script_tail": res["script_tail"][-800:]}, indent=1))
        if g["pass"]:
            (OUT / "refs").mkdir(exist_ok=True)
            (OUT / "refs" / f"{key}.sh").write_text(Path(f).read_text())
        return
    if a.explore:
        key, cmd = a.explore
        spec = spec_of(R[key])
        build(spec)
        with box(spec) as b:
            rc, out = b.sh(cmd, 300)
        print(f"rc={rc}\n{out[-12000:]}")
        return
    todo = [R[k] for k in a.only.split(",")] if a.only else list(R.values())
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for rec in ex.map(lambda r: audit(r, a.stage, a.rm), todo):
            print(summary_line(rec), flush=True)


if __name__ == "__main__":
    main()
