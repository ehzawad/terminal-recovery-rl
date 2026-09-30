"""A11 grader v2 for CLI-Gym (registration A11, A11.3).

Pass iff (b) every damage-touched live path is back to gold (added -> gone; changed/deleted -> same content hash
and mode as gold, or AST-identical for .py), (c) no start-up hook the gold image lacks, and (a) the task's tests
pass after the test-side files are made identical to gold. (b) and (c) are read on the agent's state first.

  a11_grade.py --g1                 G1: A10's references (x2) and wrong-output controls under v2 (and v1)
  a11_grade.py --episodes [KEY,..]  grade saved A11 episode change sets (v1 and v2)
"""
from __future__ import annotations

import argparse, ast, concurrent.futures as cf, hashlib, io, json, os, sys, tarfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import a10_audit as A10  # noqa: E402
from termrl import cligym  # noqa: E402
from termrl.sandbox import docker  # noqa: E402

OUT = ROOT / "results/A11"
CACHE = A10.POOL / "a11_damage"
LIVE = ["/testbed", "/opt/miniconda3", "/usr/lib", "/usr/local/lib", "/lib", "/etc/ld.so.preload", "/etc/ld.so.conf.d"]
EXCLUDE = ["/testbed/.git", "/opt/miniconda3/pkgs"]
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


def sh(b, script: str, timeout: float = 600, stdin: bytes | None = None) -> bytes:
    args = ["exec", "-i", "-u", "0:0", b.name, "bash", "-c", script]
    return docker(args, input=stdin if stdin is not None else b"", check=False, timeout=timeout).stdout or b""


def manifest(b) -> dict[str, tuple]:
    out = {}
    for line in sh(b, MANIFEST, 900).decode(errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) == 6:
            y, size, mt, mode, link, p = parts
            out[p] = (y, size, mt, mode, link)
    return out


def hashes(b, paths: list[str]) -> dict[str, str]:
    if not paths:
        return {}
    raw = sh(b, 'while IFS= read -r p; do if [ -L "$p" ]; then echo "L:$(readlink "$p")  $p"; '
                'elif [ -f "$p" ]; then sha256sum "$p"; fi; done', 900, ("\n".join(paths) + "\n").encode())
    res = {}
    for line in raw.decode(errors="replace").splitlines():
        h, _, p = line.partition("  ")
        res[p] = h
    return res


def modes(b, paths: list[str]) -> dict[str, str]:
    if not paths:
        return {}
    raw = sh(b, 'while IFS= read -r p; do [ -e "$p" ] || [ -L "$p" ] && echo "$(stat -c %a "$p")\t$p"; done', 600,
             ("\n".join(paths) + "\n").encode())
    return {p: m for m, _, p in (l.partition("\t") for l in raw.decode(errors="replace").splitlines())}


def fetch(b, paths: list[str]) -> dict[str, bytes]:
    if not paths:
        return {}
    data = sh(b, "tar -cf - --no-recursion -T - 2>/dev/null", 600, ("\n".join(paths) + "\n").encode())
    out = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            for m in t.getmembers():
                if m.isfile():
                    out["/" + m.name.lstrip("/")] = t.extractfile(m).read()
    except tarfile.TarError:
        pass
    return out


def damage_set(spec: dict) -> dict:
    """Gold-vs-damaged comparison for one task image (cached per image tag)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / (spec["image"].replace(":", "_").replace("/", "_") + ".json")
    if p.exists():
        return json.loads(p.read_text())
    with A10.box(spec, gold=True) as g:
        mg = manifest(g)
        hooks_g = sorted(set(sh(g, HOOKS).decode().split()))
        preload_g = hashes(g, ["/etc/ld.so.preload"]).get("/etc/ld.so.preload")
        tests_g = sorted(set(sh(g, TESTSIDE).decode().split()))
        tests_tar = sh(g, "cd /testbed && tar -cpf - -T -", 600, ("\n".join(tests_g) + "\n").encode())
        with A10.box(spec) as d:
            md = manifest(d)
            pkg_d = set(os.path.normpath(x) for x in sh(d, PKGFILES, 900).decode(errors="replace").splitlines() if x)
            pkg_g = set(os.path.normpath(x) for x in sh(g, PKGFILES, 900).decode(errors="replace").splitlines() if x)
            new_pkg = pkg_d - pkg_g
            added_all = sorted(p for p in md if p not in mg and md[p][0] != "d")
            added = [p for p in added_all if p not in new_pkg]
            deleted = sorted(p for p in mg if p not in md and mg[p][0] != "d")
            cand = sorted(p for p in md if p in mg and md[p][0] != "d" and md[p] != mg[p])
            dirmode = sorted(p for p in md if p in mg and md[p][0] == "d" and md[p][3] != mg[p][3])
            hg, hd = hashes(g, cand), hashes(d, cand)
            changed = sorted(p for p in cand if hg.get(p) != hd.get(p) or mg[p][3] != md[p][3] or mg[p][0] != md[p][0])
        gold_hash = hashes(g, changed + deleted)
        gold_py = {k: v.decode("utf-8", "replace") for k, v in fetch(g, [x for x in changed + deleted if x.endswith(".py")]).items()}
    res = {"image": spec["image"], "gold": spec["gold"], "added": added, "added_pkg_exempt": len(added_all) - len(added), "deleted": deleted, "changed": changed,
           "dir_mode": {p: mg[p][3] for p in dirmode}, "gold_mode": {p: mg[p][3] for p in changed + deleted},
           "gold_hash": gold_hash, "gold_py": gold_py, "hooks_gold": hooks_g, "preload_gold": preload_g,
           "tests_gold": tests_g}
    (CACHE / (p.stem + ".tests.tar")).write_bytes(tests_tar)
    p.write_text(json.dumps(res))
    return res


def same_ast(a: str, b: str) -> bool:
    try:
        return ast.dump(ast.parse(a)) == ast.dump(ast.parse(b))
    except SyntaxError:
        return False


def check_bc(b, dmg: dict) -> dict:
    fails = []
    touched = dmg["changed"] + dmg["deleted"]
    now_h, now_m = hashes(b, touched), modes(b, touched + dmg["added"] + list(dmg["dir_mode"]))
    for p in dmg["added"]:
        if p in now_m:
            fails.append(("added_still_present", p))
    py_now = fetch(b, [p for p in touched if p.endswith(".py") and now_h.get(p) != dmg["gold_hash"].get(p) and p in now_m])
    for p in touched:
        if p not in now_m:
            fails.append(("missing", p))
        elif now_h.get(p) != dmg["gold_hash"].get(p):
            if not (p.endswith(".py") and p in py_now and p in dmg["gold_py"] and
                    same_ast(py_now[p].decode("utf-8", "replace"), dmg["gold_py"][p])):
                fails.append(("content", p))
        elif now_m[p] != dmg["gold_mode"].get(p):
            fails.append(("mode", p))
    for p, m in dmg["dir_mode"].items():
        if now_m.get(p) != m:
            fails.append(("dir_mode", p))
    hooks = sorted(set(sh(b, HOOKS).decode().split()) - set(dmg["hooks_gold"]))
    for h in hooks:
        fails.append(("new_hook", h))
    if hashes(b, ["/etc/ld.so.preload"]).get("/etc/ld.so.preload") != dmg["preload_gold"]:
        fails.append(("ld_preload", "/etc/ld.so.preload"))
    return {"pass": not fails, "n_fail": len(fails), "fails": fails[:40]}


def restore_tests(b, dmg: dict) -> None:
    now = set(sh(b, TESTSIDE).decode().split())
    extra = sorted(now - set(dmg["tests_gold"]))
    if extra:
        sh(b, "cd /testbed && while IFS= read -r p; do rm -f -- \"$p\"; done", 300, ("\n".join(extra) + "\n").encode())
    tar = (CACHE / (dmg["image"].replace(":", "_").replace("/", "_") + ".tests.tar")).read_bytes()
    sh(b, "cd /testbed && tar -xpf - --overwrite", 600, tar)
    sh(b, "find /testbed -path /testbed/.git -prune -o -name .pytest_cache -type d -prune -exec rm -rf {} + ; true", 300)


def grade_v2(b, dmg: dict) -> dict:
    bc = check_bc(b, dmg)
    restore_tests(b, dmg)
    a = A10.grade(b)
    return {"pass": bc["pass"] and a["pass"], "bc": bc, "tests": {k: a[k] for k in ("pass", "rule", "summary", "n_pass", "n_ids", "timeout")}}


def g1_task(key: str) -> dict:
    row = A10.rows()[key]
    spec = A10.spec_of(row)
    ok, msg = A10.build(spec)
    if not ok:
        return {"key": key, "error": "build: " + msg[-300:]}
    dmg = damage_set(spec)
    out = {"key": key, "damage": {k: len(dmg[k]) for k in ("added", "deleted", "changed")} | {"dir_mode": len(dmg["dir_mode"])}}
    ref = (A10.OUT / "refs" / f"{key}.sh").read_text()
    mut = (A10.OUT / "mutants" / f"{key}.sh").read_text()
    out["ref"] = []
    for _ in range(2):
        with A10.box(spec) as b:
            b.sh(ref, 900)
            out["ref"].append(grade_v2(b, dmg))
    with A10.box(spec) as b:
        b.sh(mut, 900)
        out["mutant"] = grade_v2(b, dmg)
    return out


def g1(jobs: int) -> None:
    keys = [k for k in A10.rows() if (A10.OUT / "refs" / f"{k}.sh").exists() and (A10.OUT / "mutants" / f"{k}.sh").exists()]
    (OUT / "g1").mkdir(parents=True, exist_ok=True)
    todo = [k for k in keys if not (OUT / "g1" / f"{k}.json").exists()]
    print(len(keys), "tasks with reference and control;", len(todo), "to run", flush=True)

    def work(k):
        try:
            r = g1_task(k)
        except Exception as e:
            r = {"key": k, "error": repr(e)[:500]}
        (OUT / "g1" / f"{k}.json").write_text(json.dumps(r, indent=1))
        spec = A10.spec_of(A10.rows()[k])
        docker(["image", "rm", "-f", spec["image"]], check=False, timeout=300)
        return r

    with cf.ThreadPoolExecutor(jobs) as ex:
        for r in ex.map(work, todo):
            if "error" in r:
                print(r["key"][8:70], "ERROR", r["error"][:200], flush=True)
                continue
            f = lambda g: ("P" if g["pass"] else "F") + ("" if g["bc"]["pass"] else "b") + ("" if g["tests"]["pass"] else "t")
            print(f"{r['key'][8:70]:62} dmg={r['damage']} ref={','.join(f(g) for g in r['ref'])} mut={f(r['mutant'])}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--g1", action="store_true")
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args()
    if a.g1:
        g1(a.jobs)


if __name__ == "__main__":
    main()
