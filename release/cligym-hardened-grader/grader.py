"""Hardened grader for CLI-Gym (LiberCoders/CLI-Gym) environment-repair tasks.

A CLI-Gym task is a healthy ("gold") SWE-smith image plus Dockerfile lines that break it, graded by a list of
pytest IDs inside the repository. That grading can be passed without repairing anything (editing tests, a
conftest or sitecustomize that undoes the damage only under pytest, partial repairs). This grader passes a
container only if all three hold:

  1. damage undone   - every code file the task's Dockerfile added, changed or deleted relative to gold is back
                       to gold (removed if added; byte-identical, or AST-identical for .py, otherwise; same mode).
                       Files of packages the Dockerfile installed as tools, `.git`, and the conda package cache
                       are ignored; added/deleted non-code files are ignored, changed files of any type count.
  2. no new hooks    - no `.pth`, `sitecustomize.py`, `usercustomize.py` absent from gold; `/etc/ld.so.preload`
                       as in gold.
  3. tests pass      - after every test-side file under /testbed is made identical to gold, the task's own
                       pytest IDs all pass.

Checks 1 and 2 read the container as the agent left it, before check 3 restores the tests.

Usage (needs docker and the dataset parquet):
  python grader.py grade --parquet train.parquet --task TASK_ID [--script repair.sh]
      builds the task, starts a fresh offline container, runs the optional script inside it as root in /testbed,
      then grades. Prints JSON. Exit status 0 = pass.
  Set DOCKER="sudo docker" (or similar) if docker needs a prefix.

Library use: build(task) -> (damaged_tag, gold_tag); damage = damage_set(task); with Container(tag) as c: ...;
grade(c, task, damage).
"""
from __future__ import annotations

import argparse, ast, hashlib, io, json, os, re, shlex, subprocess, sys, tarfile, tempfile
from pathlib import Path

DOCKER = shlex.split(os.environ.get("DOCKER", "docker"))
CACHE = Path(os.environ.get("CLIGYM_GRADER_CACHE", Path.home() / ".cache" / "cligym-grader"))
LIVE = ["/testbed", "/opt/miniconda3", "/usr/lib", "/usr/local/lib", "/lib", "/etc/ld.so.preload", "/etc/ld.so.conf.d"]
TEST_TIMEOUT = 1500

MANIFEST = r"""
for d in %s; do [ -e "$d" ] || continue; [ -L "$d" ] && [ -d "$d" ] && continue
  find "$d" -xdev \( -path /testbed/.git -o -path /opt/miniconda3/pkgs -o -name __pycache__ -o -name .pytest_cache \) -prune \
    -o \( -type f ! -name '*.pyc' -o -type l -o -type d \) -printf '%%y\t%%s\t%%T@\t%%m\t%%l\t%%p\n'
done
""" % " ".join(LIVE)
HOOKS = r"""find /opt/miniconda3 /usr/lib /usr/local/lib -xdev -path /opt/miniconda3/pkgs -prune -o \
  \( -name '*.pth' -o -name sitecustomize.py -o -name usercustomize.py \) -path '*-packages*' -print 2>/dev/null
find /opt/miniconda3 /usr/lib /usr/local/lib -xdev -path /opt/miniconda3/pkgs -prune -o \
  \( -name sitecustomize.py -o -name usercustomize.py \) -print 2>/dev/null; true"""
PKGFILES = r"""cat /var/lib/dpkg/info/*.list 2>/dev/null
for r in $(find /opt/miniconda3 /usr/lib /usr/local/lib -xdev -path /opt/miniconda3/pkgs -prune -o -path '*.dist-info/RECORD' -print 2>/dev/null); do
  base=$(dirname "$(dirname "$r")"); cut -d, -f1 "$r" | sed "s|^|$base/|"; done; true"""
TESTSIDE = r"""cd /testbed && find . -path ./.git -prune -o -type f \( -path '*/tests/*' -o -path '*/test/*' -o -name 'test_*.py' \
  -o -name '*_test.py' -o -name conftest.py -o -name pytest.ini -o -name tox.ini -o -name setup.cfg -o -name pyproject.toml \
  -o -name .coveragerc \) ! -path '*/__pycache__/*' ! -name '*.pyc' -print"""
PYTEST_CALL = re.compile(r"pytest --disable-warnings[^']*?--verbose ([^']*)'")
LINE = re.compile(r"^(\S+::\S+?)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b", re.M)
SUMMARY = re.compile(r"^=+ (.*(?:passed|failed|error|no tests ran).*) in [\d.]+s", re.M)


def docker(args: list[str], *, input: bytes | None = None, timeout: float = 600, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(DOCKER + args, input=input if input is not None else b"", capture_output=True, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args[:2])}: {p.stderr.decode(errors='replace')[-800:]}")
    return p


# ---------------------------------------------------------------- tasks and images
def load_task(parquet: str, task_id: str) -> dict:
    import pandas as pd
    r = pd.read_parquet(parquet).set_index("task_id").loc[task_id]
    return {"task_id": task_id, "dockerfile": r.dockerfile, "run_tests": r.run_tests, "task_yaml": r.task_yaml,
            "gold": re.search(r"^FROM\s+(\S+)", r.dockerfile, re.M).group(1)}


def build(task: dict) -> tuple[str, str]:
    """Build the damaged image (network on). Returns (damaged_tag, gold_tag)."""
    tag = "cligym-grader:" + hashlib.sha256(task["dockerfile"].encode()).hexdigest()[:16]
    if docker(["image", "inspect", tag], check=False, timeout=60).returncode != 0:
        with tempfile.TemporaryDirectory() as d:
            Path(d, "Dockerfile").write_text(task["dockerfile"])
            docker(["build", "-q", "-t", tag, d], timeout=3600)
    return tag, task["gold"]


class Container:
    """Offline container, 2 pinned CPUs, 4 GB, kept alive with sleep; commands run as root in /testbed."""

    def __init__(self, image: str, cpus: str = "0,1"):
        self.name = "cligym-" + os.urandom(6).hex()
        docker(["run", "-d", "--name", self.name, "--network", "none", "--cpuset-cpus", cpus, "--memory", "4g",
                "--memory-swap", "4g", "--pids-limit", "1024", "--workdir", "/testbed", "--entrypoint", "/bin/sh",
                image, "-c", "exec sleep infinity"])

    def sh(self, script: str, timeout: float = 900, stdin: bytes | None = None) -> tuple[int | None, bytes]:
        if stdin is None:
            args, data = ["exec", "-i", "-u", "0:0", "-w", "/testbed", self.name, "bash", "-s"], script.encode()
        else:
            args, data = ["exec", "-i", "-u", "0:0", "-w", "/testbed", self.name, "bash", "-c", script], stdin
        try:
            p = docker(args, input=data, check=False, timeout=timeout)
            return p.returncode, (p.stdout or b"") + (p.stderr or b"")
        except subprocess.TimeoutExpired:
            return None, b"TIMEOUT"

    def out(self, script: str, stdin: bytes | None = None, timeout: float = 900) -> bytes:
        return self.sh(script, timeout, stdin if stdin is not None else b"")[1]

    def close(self):
        docker(["rm", "-f", self.name], check=False, timeout=120)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


# ---------------------------------------------------------------- the dataset's own tests
def run_tests(c: Container, task: dict) -> dict:
    m = PYTEST_CALL.search(task["run_tests"])
    ids = m.group(1).split() if m else []
    rc, out = c.sh("cat > /tmp/.run_tests.sh <<'CLIGYMEOF'\n" + task["run_tests"] + "\nCLIGYMEOF\n"
                   "cd /testbed && bash /tmp/.run_tests.sh >/tmp/.rt.out 2>&1; cat /test.log 2>/dev/null", TEST_TIMEOUT)
    text = out.decode(errors="replace")
    norm = lambda s: s.replace("\\", "")
    seen = {norm(x.group(1)): x.group(2) for x in LINE.finditer(text)}
    status = {i: seen.get(norm(i), "MISSING") for i in ids}
    tail = SUMMARY.findall(text)
    counts = {k: int(n) for n, k in re.findall(r"(\d+) (passed|failed|error|errors|skipped)", tail[-1])} if tail else {}
    bad = ("failed", "error", "errors") + (("skipped",) if ids else ())
    by_summary = (counts.get("passed", 0) > 0 if not ids else counts.get("passed") == len(ids)) and not any(counts.get(k) for k in bad)
    by_ids = bool(ids) and all(v == "PASSED" for v in status.values())
    return {"pass": rc is not None and (by_ids or by_summary), "n_ids": len(ids),
            "not_passed": {k: v for k, v in status.items() if v != "PASSED"}, "summary": tail[-1] if tail else None,
            "timeout": rc is None}


# ---------------------------------------------------------------- damage set (gold vs damaged)
def _manifest(c: Container) -> dict:
    out = {}
    for line in c.out(MANIFEST).decode(errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) == 6:
            out[parts[5]] = tuple(parts[:5])
    return out


def _hashes(c: Container, paths: list[str]) -> dict:
    if not paths:
        return {}
    raw = c.out('while IFS= read -r p; do if [ -L "$p" ]; then echo "L:$(readlink "$p")  $p"; '
                'elif [ -f "$p" ]; then sha256sum "$p"; fi; done', ("\n".join(paths) + "\n").encode())
    return {p: h for h, _, p in (l.partition("  ") for l in raw.decode(errors="replace").splitlines())}


def _modes(c: Container, paths: list[str]) -> dict:
    if not paths:
        return {}
    raw = c.out('while IFS= read -r p; do { [ -e "$p" ] || [ -L "$p" ]; } && echo "$(stat -c %a "$p")\t$p"; done',
                ("\n".join(paths) + "\n").encode())
    return {p: m for m, _, p in (l.partition("\t") for l in raw.decode(errors="replace").splitlines())}


def _fetch(c: Container, paths: list[str]) -> dict:
    if not paths:
        return {}
    data = c.out("tar -cf - --no-recursion -T - 2>/dev/null", ("\n".join(paths) + "\n").encode())
    out = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            for m in t.getmembers():
                if m.isfile():
                    out["/" + m.name.lstrip("/")] = t.extractfile(m).read()
    except tarfile.TarError:
        pass
    return out


def _pkg_paths(c: Container) -> set:
    out = set()
    for x in c.out(PKGFILES).decode(errors="replace").splitlines():
        if x:
            p = os.path.normpath(x)
            out.add(p)
            for top in ("/lib", "/bin", "/sbin", "/lib64"):
                if p.startswith(top + "/"):
                    out.add("/usr" + p)
    return out


def damage_set(task: dict) -> dict:
    """What the Dockerfile did relative to gold, plus the gold copies the check needs. Cached per Dockerfile."""
    damaged, gold = build(task)
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(task["dockerfile"].encode()).hexdigest()[:16]
    p = CACHE / f"{key}.json"
    if p.exists():
        return json.loads(p.read_text())
    with Container(gold) as g, Container(damaged) as d:
        mg, md = _manifest(g), _manifest(d)
        new_pkg = _pkg_paths(d) - _pkg_paths(g)
        added = sorted(x for x in md if x not in mg and md[x][0] != "d" and x not in new_pkg)
        deleted = sorted(x for x in mg if x not in md and mg[x][0] != "d")
        cand = sorted(x for x in md if x in mg and md[x][0] != "d" and md[x] != mg[x])
        hg, hd = _hashes(g, cand), _hashes(d, cand)
        changed = sorted(x for x in cand if hg.get(x) != hd.get(x) or mg[x][3] != md[x][3] or mg[x][0] != md[x][0])
        dirmode = {x: mg[x][3] for x in md if x in mg and md[x][0] == "d" and md[x][3] != mg[x][3]}
        gold_hash = _hashes(g, changed + deleted)
        gold_py = {k: v.decode("utf-8", "replace") for k, v in _fetch(g, [x for x in changed + deleted if x.endswith(".py")]).items()}
        tests = sorted(set(g.out(TESTSIDE).decode().split()))
        tests_tar = g.out("cd /testbed && tar -cpf - -T -", ("\n".join(tests) + "\n").encode())
        res = {"added": added, "deleted": deleted, "changed": changed, "dir_mode": dirmode,
               "gold_mode": {x: mg[x][3] for x in changed + deleted}, "gold_hash": gold_hash, "gold_py": gold_py,
               "hooks_gold": sorted(set(g.out(HOOKS).decode().split())),
               "preload_gold": _hashes(g, ["/etc/ld.so.preload"]).get("/etc/ld.so.preload"), "tests_gold": tests}
    (CACHE / f"{key}.tests.tar").write_bytes(tests_tar)
    p.write_text(json.dumps(res))
    return res


# ---------------------------------------------------------------- the check
def _is_code(p: str) -> bool:
    n = p.rsplit("/", 1)[-1]
    return n.endswith((".py", ".pth", ".so")) or ".so." in n or "/bin/" in p or "/sbin/" in p or p.startswith("/etc/ld.so")


def _same_ast(a: str, b: str) -> bool:
    try:
        return ast.dump(ast.parse(a)) == ast.dump(ast.parse(b))
    except SyntaxError:
        return False


def residue(c: Container, dmg: dict) -> list:
    """Checks 1 and 2 on the container as it stands. Returns a list of (problem, path); empty means clean."""
    fails = []
    added = [p for p in dmg["added"] if _is_code(p)]
    touched = dmg["changed"] + [p for p in dmg["deleted"] if _is_code(p)]
    now_h, now_m = _hashes(c, touched), _modes(c, touched + added + list(dmg["dir_mode"]))
    fails += [("added_still_present", p) for p in added if p in now_m]
    py_now = _fetch(c, [p for p in touched if p.endswith(".py") and p in now_m and now_h.get(p) != dmg["gold_hash"].get(p)])
    for p in touched:
        if p not in now_m:
            fails.append(("missing", p))
        elif now_h.get(p) != dmg["gold_hash"].get(p):
            if not (p in py_now and p in dmg["gold_py"] and _same_ast(py_now[p].decode("utf-8", "replace"), dmg["gold_py"][p])):
                fails.append(("content", p))
        elif now_m[p] != dmg["gold_mode"].get(p):
            fails.append(("mode", p))
    fails += [("dir_mode", p) for p, m in dmg["dir_mode"].items() if now_m.get(p) != m]
    fails += [("new_hook", h) for h in sorted(set(c.out(HOOKS).decode().split()) - set(dmg["hooks_gold"]))]
    if _hashes(c, ["/etc/ld.so.preload"]).get("/etc/ld.so.preload") != dmg["preload_gold"]:
        fails.append(("ld_preload", "/etc/ld.so.preload"))
    return fails


def restore_tests(c: Container, task: dict, dmg: dict) -> None:
    extra = sorted(set(c.out(TESTSIDE).decode().split()) - set(dmg["tests_gold"]))
    if extra:
        c.out('cd /testbed && while IFS= read -r p; do rm -f -- "$p"; done', ("\n".join(extra) + "\n").encode())
    key = hashlib.sha256(task["dockerfile"].encode()).hexdigest()[:16]
    c.out("cd /testbed && tar -xpf - --overwrite", (CACHE / f"{key}.tests.tar").read_bytes())
    c.out("find /testbed -path /testbed/.git -prune -o -name .pytest_cache -type d -prune -exec rm -rf {} + ; true")


def grade(c: Container, task: dict, dmg: dict) -> dict:
    """Grade a container in place (it is modified: test-side files are restored before the tests run)."""
    res = residue(c, dmg)
    restore_tests(c, task, dmg)
    t = run_tests(c, task)
    return {"pass": not res and t["pass"], "residue": res[:40], "tests": t}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grade")
    g.add_argument("--parquet", required=True)
    g.add_argument("--task", required=True)
    g.add_argument("--script", help="bash script to run in the fresh container before grading (a repair attempt)")
    g.add_argument("--dataset-grader", action="store_true", help="also report the dataset's own verdict (fresh container)")
    a = ap.parse_args()
    task = load_task(a.parquet, a.task)
    damaged, _ = build(task)
    dmg = damage_set(task)
    out = {"task": a.task}
    if a.dataset_grader:
        with Container(damaged) as c:
            if a.script:
                c.sh(Path(a.script).read_text())
            out["dataset_grader"] = run_tests(c, task)
    with Container(damaged) as c:
        if a.script:
            rc, log = c.sh(Path(a.script).read_text())
            out["script_rc"] = rc
        out["hardened"] = grade(c, task, dmg)
    print(json.dumps(out, indent=1))
    sys.exit(0 if out["hardened"]["pass"] else 1)


if __name__ == "__main__":
    main()
