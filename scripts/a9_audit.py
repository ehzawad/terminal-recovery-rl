"""A9 executable audit of sampled tasks from SETA-Env, TMax-15K and LiteCoder-Terminal-RL-preview.

Per task: build the image (network on), then in fresh offline containers run the no-op grade, two
reference runs and, when a `mutants/<key>.sh` exists, the reviewer-written wrong-output control.
Records go to results/A9/records/<key>.json.  Usage: a9_audit.py [--only KEY,..] [--jobs N] [--mutants-only]
"""
from __future__ import annotations

import argparse, concurrent.futures as cf, hashlib, json, os, re, shlex, shutil, subprocess, sys, tempfile, textwrap, time, tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from termrl.sandbox import docker  # noqa: E402

POOL = Path("/mnt/sdb/arafat/ehz/llm/.pools/audit9")
VT = Path("/mnt/sdb/arafat/ehz/llm/.venvs/vt")
OUT = ROOT / "results/A9"
BUILD = POOL / "build"
NET_PAT = re.compile(r"Could not resolve|Temporary failure in name resolution|Network is unreachable|curl: \(6\)|curl: \(7\)|"
                     r"Name or service not known|Connection refused|Failed to fetch|Unable to locate package|"
                     r"Max retries exceeded|urlopen error|ConnectionError|No route to host|pip.*ERROR: (Could not find|No matching)", re.I)
HARNESS = re.compile(r"openhands|nvm|claude-code|asciinema|astral\.sh/uv|uv (venv|python)", re.I)


def key_of(ds: str, task: str) -> str:
    return f"{ds}__{task}"


def sample() -> list[dict]:
    s = json.load(open(OUT / "sample.json"))
    rows = []
    for ds in ("SETA", "TMax", "LiteCoder"):
        for i, x in enumerate(s[ds]):
            rows.append({"ds": ds, "task": x["task"], "subset": x.get("subset"), "idx": i, "key": key_of(ds, x["task"])})
    return rows


def task_src(r: dict) -> Path:
    if r["ds"] == "SETA":
        return POOL / "SETA-sample" / r["subset"] / r["task"]
    if r["ds"] == "TMax":
        return POOL / "TMax-sample" / r["task"]
    return POOL / "LiteCoder-Terminal-RL-preview" / r["task"]


def parse_def(text: str) -> dict:
    secs, cur = {"header": []}, "header"
    for line in text.splitlines():
        m = re.match(r"^%(\w+)\s*$", line)
        if m:
            cur = m.group(1)
            secs.setdefault(cur, [])
        else:
            secs[cur].append(line)
    return secs


def prepare(r: dict) -> dict:
    """Return the run spec and write the docker build context."""
    src, ctx = task_src(r), BUILD / r["key"]
    if ctx.exists():
        shutil.rmtree(ctx)
    spec = {"notes": []}
    if r["ds"] in ("SETA", "LiteCoder"):
        shutil.copytree(src / "environment", ctx)
        df = (ctx / "Dockerfile").read_text()
        if r["ds"] == "LiteCoder":
            keep, drop = [], []
            blocks = re.split(r"\n(?=(?:RUN|ENV|COPY|FROM|WORKDIR|ADD|CMD|ENTRYPOINT|USER|ARG)\b)", df)
            for b in blocks:
                (drop if HARNESS.search(b) and b.split()[0] in ("RUN", "ENV") and "apt-get install" not in b else keep).append(b)
            df = "\n".join(keep) + "\n"
            spec["notes"].append(f"removed {len(drop)} agent-harness Dockerfile blocks")
            (ctx / "Dockerfile").write_text(df)
        wd = re.findall(r"^\s*WORKDIR\s+(\S+)", df, re.M)
        spec["workdir"] = wd[-1] if wd else "/"
        spec["user"] = (re.findall(r"^\s*USER\s+(\S+)", df, re.M) or ["0:0"])[-1]
        spec["tests_dir"] = str(src / "tests")
        spec["test_file"] = "test_outputs.py"
        spec["grader"] = "toolchain"
        spec["ref_kind"] = "solve.sh"
        spec["ref_dir"] = str(src / "solution")
        toml = tomllib.load(open(src / "task.toml", "rb"))
        spec["verifier_timeout"] = min(float(toml.get("verifier", {}).get("timeout_sec", 600)), 600)
        spec["instruction"] = (src / "instruction.md").read_text()
    else:
        d = parse_def((src / "container.def").read_text())
        frm = re.search(r"^From:\s*(\S+)", "\n".join(d["header"]), re.M).group(1)
        lines = [f"FROM {frm}"]
        copies = []
        for ln in d.get("files", []):
            ln = ln.strip()
            if not ln:
                continue
            a, b = ln.split(None, 1)
            m = re.search(re.escape(r["task"]) + r"/(.+)$", a)
            if not m:
                spec["notes"].append(f"unmapped %files source {a}")
                continue
            copies.append((m.group(1), b.strip()))
        shutil.copytree(src, ctx, ignore=shutil.ignore_patterns("solutions", "container.def"))
        for s_, d_ in copies:
            lines.append(f"COPY {shlex.quote(s_)} {shlex.quote(d_)}")
        post = textwrap.dedent("\n".join(d.get("post", [])))
        (ctx / "post.sh").write_text(post + "\n")
        lines += ["COPY post.sh /tmp/post.sh", "RUN /bin/sh -e /tmp/post.sh && rm -f /tmp/post.sh"]
        env = [l.strip() for l in d.get("environment", []) if l.strip()]
        if env:
            (ctx / "envfile.sh").write_text("\n".join(env) + "\n")
            spec["notes"].append("has %environment (written to /etc/profile.d, not applied to exec env)")
            lines.append("COPY envfile.sh /etc/profile.d/a9env.sh")
        (ctx / "Dockerfile").write_text("\n".join(lines) + "\n")
        start = [l for l in d.get("startscript", []) if l.strip()]
        spec["startscript"] = "\n".join(start) if start else None
        spec["workdir"] = "/home/user" if "/home/user" in post else "/"
        spec["user"] = "0:0"
        spec["tests_dir"] = str(ctx)
        spec["test_file"] = "test_final_state.py"
        spec["initial_test_file"] = "test_initial_state.py"
        spec["grader"] = "image-pytest"
        spec["ref_kind"] = "replay"
        spec["verifier_timeout"] = 300
        spec["instruction"] = json.load(open(src / "task.json"))["description"]
        summ = src / "solutions/gemini_gemini-3-flash-preview_summary.json"
        spec["replay"] = None
        if summ.exists():
            res = json.load(open(summ))["results"]
            ok = [x for x in res if x["success"]]
            spec["gemini"] = {"runs": len(res), "success": len(ok)}
            if ok:
                best = min(ok, key=lambda x: len(x["messages"]))
                cmds = []
                for m in best["messages"]:
                    for tc in (m.get("tool_calls") or []):
                        try:
                            c = json.loads(tc["function"]["arguments"]).get("command")
                        except Exception:
                            c = None
                        if c:
                            cmds.append(c)
                cmds = [c for c in cmds if "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" not in c]
                spec["replay"] = cmds
        else:
            spec["gemini"] = None
    h = hashlib.sha256()
    for p in sorted(ctx.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(ctx)).encode()); h.update(p.read_bytes())
    spec["image"] = f"a9:{re.sub(r'[^a-z0-9_.-]', '-', r['key'].lower())[:80]}-{h.hexdigest()[:10]}"
    spec["ctx"] = str(ctx)
    return spec


def build(spec: dict) -> tuple[bool, str]:
    if docker(["image", "inspect", spec["image"]], check=False, timeout=60).returncode == 0:
        return True, "cached"
    t0 = time.time()
    try:
        p = docker(["build", "-q", "-t", spec["image"], spec["ctx"]], check=False, timeout=1800)
    except subprocess.TimeoutExpired:
        return False, "build timeout"
    if p.returncode != 0:
        return False, (p.stderr or b"").decode(errors="replace")[-1500:]
    return True, f"built in {time.time()-t0:.0f}s"


class Box:
    def __init__(self, spec: dict):
        self.spec = spec
        self.name = "a9" + hashlib.sha256(os.urandom(16)).hexdigest()[:12]
        docker(["run", "-d", "--name", self.name, "--network", "none", "--cpus", "2", "--memory", "4g", "--memory-swap", "4g",
                "--pids-limit", "1024", "--cap-drop", "NET_RAW", "-v", f"{VT}:/opt/vt:ro", "--workdir", spec["workdir"],
                "--entrypoint", "/bin/sh", spec["image"], "-c", "exec sleep infinity"], timeout=300)
        docker(["exec", "-u", "0:0", self.name, "sh", "-c", "mkdir -p /logs/verifier"], check=False, timeout=60)
        if spec.get("startscript"):
            docker(["exec", "-d", "-u", "0:0", self.name, "sh", "-c", spec["startscript"] + " >/tmp/.start.log 2>&1"], check=False, timeout=60)
            time.sleep(2)

    def sh(self, script: str, timeout: float, cwd: str | None = None, user: str = "0:0", env: dict | None = None) -> tuple[int | None, str]:
        args = ["exec", "-i", "-u", user, "-w", cwd or self.spec["workdir"]]
        for k, v in (env or {}).items():
            args += ["-e", f"{k}={v}"]
        args += [self.name, "bash", "-s"]
        try:
            p = docker(args, input=script.encode(), check=False, timeout=timeout)
            return p.returncode, ((p.stdout or b"") + (p.stderr or b"")).decode(errors="replace")
        except subprocess.TimeoutExpired:
            return None, f"TIMEOUT after {timeout:.0f}s"

    def put_dir(self, host: str, dest: str) -> None:
        docker(["exec", "-u", "0:0", self.name, "sh", "-c", f"rm -rf {shlex.quote(dest)} && mkdir -p {shlex.quote(dest)}"], timeout=60)
        with tempfile.TemporaryDirectory() as t:
            tar = os.path.join(t, "x.tar")
            subprocess.run(["tar", "-C", host, "--exclude", "__pycache__", "-cf", tar, "."], check=True)
            docker(["cp", tar, f"{self.name}:/tmp/.a9.tar"], timeout=120)
        docker(["exec", "-u", "0:0", self.name, "sh", "-c", f"tar -C {shlex.quote(dest)} -xf /tmp/.a9.tar && rm -f /tmp/.a9.tar"], timeout=120)

    def close(self) -> None:
        docker(["rm", "-f", self.name], check=False, timeout=120)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


OUTCOME = re.compile(r"^(PASSED|FAILED|ERROR)\s+(\S+)", re.M)


def pytest_cmd(spec: dict, file: str) -> str:
    f = f"/tests/{file}"
    if spec["grader"] == "toolchain":
        return (f"export PATH=/opt/vt/python/bin:$PATH PYTHONPATH=/opt/vt/site; cd {shlex.quote(spec['workdir'])}; "
                f"python3 -m pytest -p no:cacheprovider --rootdir=/tests {f} -rA -q 2>&1")
    return f"cd {shlex.quote(spec['workdir'])}; python3 -m pytest -p no:cacheprovider --rootdir=/tests {f} -rA -q 2>&1"


def grade(box: Box, file: str | None = None) -> dict:
    spec = box.spec
    box.put_dir(spec["tests_dir"], "/tests")
    t0 = time.time()
    rc, out = box.sh(pytest_cmd(spec, file or spec["test_file"]), spec["verifier_timeout"], cwd="/")
    tests = {m.group(2): m.group(1) for m in OUTCOME.finditer(out)}
    return {"pytest_rc": rc, "pass": rc == 0, "tests": tests, "n_pass": sum(v == "PASSED" for v in tests.values()),
            "n_fail": sum(v != "PASSED" for v in tests.values()), "seconds": round(time.time() - t0, 1), "log_tail": out[-1800:]}


def run_reference(box: Box) -> tuple[int | None, str, str]:
    spec = box.spec
    if spec["ref_kind"] == "solve.sh":
        box.put_dir(spec["ref_dir"], "/solution")
        rc, out = box.sh("bash /solution/solve.sh", 600)
        return rc, out[-1500:], "solve.sh"
    if not spec.get("replay"):
        return None, "no recorded successful rollout", "none"
    rc, out = box.sh("\n".join(spec["replay"]) + "\n", 600)
    return rc, out[-1500:], f"replay of {len(spec['replay'])} commands"


def run_mutant(box: Box, script: str) -> tuple[int | None, str]:
    return box.sh(script, 600)


def audit(r: dict, mutants_only: bool = False) -> dict:
    rec_path = OUT / "records" / f"{r['key']}.json"
    rec = json.load(open(rec_path)) if (mutants_only and rec_path.exists()) else {"key": r["key"], "ds": r["ds"], "task": r["task"]}
    spec = prepare(r)
    rec["notes"] = spec["notes"]
    rec["workdir"], rec["instruction_chars"] = spec["workdir"], len(spec["instruction"])
    rec["gemini"] = spec.get("gemini")
    ok, msg = build(spec)
    rec["build"] = {"ok": ok, "msg": msg[-1500:]}
    if not ok:
        rec["status"] = "build_failed"
        return rec
    if not mutants_only:
        if spec.get("initial_test_file"):
            with Box(spec) as b:
                rec["initial_state"] = grade(b, spec["initial_test_file"])
        with Box(spec) as b:
            rec["noop"] = grade(b)
        rec["ref"] = []
        for i in range(2):
            with Box(spec) as b:
                rc, out, how = run_reference(b)
                g = grade(b) if how != "none" else None
                rec["ref"].append({"how": how, "rc": rc, "run_tail": out, "grade": g,
                                   "network_error": bool(NET_PAT.search(out or "") or (g and NET_PAT.search(g["log_tail"])))})
            if how == "none":
                break
    mut = ROOT / "results/A9/mutants" / f"{r['key']}.sh"
    if mut.exists():
        with Box(spec) as b:
            rc, out = run_mutant(b, mut.read_text())
            rec["mutant"] = {"rc": rc, "run_tail": out[-800:], "grade": grade(b)}
    rec["status"] = "done"
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--mutants-only", action="store_true")
    a = ap.parse_args()
    (OUT / "records").mkdir(parents=True, exist_ok=True)
    rows = sample()
    if a.only:
        want = set(a.only.split(","))
        rows = [r for r in rows if r["key"] in want or r["ds"] in want or f"{r['ds']}:{r['idx']}" in want]
    def one(r):
        t0 = time.time()
        try:
            rec = audit(r, a.mutants_only)
        except Exception as e:  # recorded, never swallowed
            rec = {"key": r["key"], "ds": r["ds"], "task": r["task"], "status": "harness_error", "error": repr(e)[-1500:]}
        rec["wall_s"] = round(time.time() - t0, 1)
        json.dump(rec, open(OUT / "records" / f"{r['key']}.json", "w"), indent=1)
        print(r["key"], rec["status"], rec["wall_s"], flush=True)
        return rec
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(one, rows))


if __name__ == "__main__":
    main()
