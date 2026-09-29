"""A9 static screen: model-free, no container. Flags for human/agent review, not verdicts."""
from __future__ import annotations

import ast, json, re, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import a9_audit as A  # noqa: E402

NET = re.compile(r"\b(curl|wget|git clone|pip3? install|npm (i|install)|apt(-get)? (update|install)|uv (add|pip|sync)|gem install|go get|cargo install)\b")
GPU = re.compile(r"nvidia|cuda|torch\.cuda|--gpus|\btensorflow-gpu\b", re.I)
PRIV = re.compile(r"--privileged|\bmount\b|iptables|\bsystemctl\b|/var/run/docker\.sock|\bmodprobe\b|\binsmod\b|\bsysctl -w\b|/proc/sys|\bchroot\b", re.I)
DANGER = re.compile(r"rm\s+-rf?\s+(/|~|\$HOME)\s|rm\s+-rf?\s+/\*|mkfs|dd\s+if=.*of=/dev/|:\(\)\s*\{|chmod\s+-R\s+777\s+/\s|>\s*/dev/sd|curl[^|\n]*\|\s*(ba)?sh", re.I)
EXPO_NAMES = re.compile(r"(solution|solve|expected|answer|golden|reference|oracle|\.test|test_)", re.I)


def literals(path: Path) -> set[str]:
    out = set()
    try:
        for n in ast.walk(ast.parse(path.read_text())):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                for line in n.value.splitlines():
                    line = line.strip()
                    if len(line) >= 18 and not line.startswith(("/", "http")) and re.search(r"[A-Za-z]{4}", line):
                        out.add(line)
    except SyntaxError:
        pass
    return out


def visible_text(spec: dict, r: dict) -> dict[str, str]:
    ctx = Path(spec["ctx"])
    files = {}
    for p in ctx.rglob("*"):
        if p.is_file() and p.stat().st_size < 400_000:
            rel = str(p.relative_to(ctx))
            if r["ds"] == "TMax" and rel.startswith(("test_", "task.json", "task_summary")):
                continue
            try:
                files[rel] = p.read_text()
            except UnicodeDecodeError:
                pass
    return files


def screen(r: dict) -> dict:
    spec = A.prepare(r)
    src = A.task_src(r)
    vis = visible_text(spec, r)
    tests = Path(spec["tests_dir"]) / spec["test_file"]
    lits = literals(tests)
    hits = []
    for lit in sorted(lits):
        for rel, txt in vis.items():
            if lit in txt and rel != "Dockerfile":
                hits.append({"literal": lit[:120], "file": rel})
                break
    names = [rel for rel in vis if EXPO_NAMES.search(Path(rel).name) and not rel.startswith("post.sh")]
    ref_text = ""
    if r["ds"] == "TMax":
        ref_text = " ".join(spec.get("replay") or [])
        build_text = vis.get("post.sh", "") + vis.get("Dockerfile", "")
        run_text = ref_text + (Path(spec["tests_dir"]) / spec["test_file"]).read_text()
    else:
        ref_text = (src / "solution/solve.sh").read_text()
        build_text = vis.get("Dockerfile", "")
        run_text = ref_text + tests.read_text()
    wrapper = (src / "tests/test.sh").read_text() if (src / "tests/test.sh").exists() else ""
    return {
        "key": r["key"],
        "n_visible_files": len(vis),
        "exposure_literal_hits": hits[:8], "n_exposure_literal_hits": len(hits), "n_test_literals": len(lits),
        "exposure_named_files": names[:8],
        "build_network": sorted(set(m.group(0) for m in NET.finditer(build_text))),
        "runtime_network_in_reference_or_tests": sorted(set(m.group(0) for m in NET.finditer(run_text))),
        "wrapper_fetches": sorted(set(m.group(0) for m in NET.finditer(wrapper))),
        "gpu": bool(GPU.search(build_text + run_text)), "privilege": sorted(set(m.group(0) for m in PRIV.finditer(build_text + run_text))),
        "danger": sorted(set(m.group(0)[:40] for m in DANGER.finditer(build_text + run_text))),
        "instruction_words": len(spec["instruction"].split()),
        "tests_lines": tests.read_text().count("\n"),
    }


def tmax_corpus() -> dict:
    p = A.POOL / "TMax-15K"
    z = zipfile.ZipFile(p / "tasks.zip")
    names = z.namelist()
    ids = {n.split("/")[0] for n in names if n.endswith("/task.json")}
    g = {n.split("/")[0] for n in names if n.endswith("gemini_gemini-3-flash-preview_summary.json")}
    succ = set()
    dist = {}
    for n in names:
        if n.endswith("gemini_gemini-3-flash-preview_summary.json"):
            d = json.loads(z.read(n))
            dist[n.split("/")[0]] = (d["num_success"], d["num_runs"])
            if d["num_success"] > 0:
                succ.add(n.split("/")[0])
    gp = gp_files = net_post = 0
    for i in sorted(ids):
        c = z.read(f"{i}/container.def").decode(errors="replace")
        gp += "/gpfs/" in c
        post = c.split("%post", 1)[-1]
        net_post += bool(NET.search(post))
    nonempty_ref = sum(1 for n in names if n.endswith("/solutions/summary.json") and z.getinfo(n).file_size > 2)
    from collections import Counter
    return {"tasks": len(ids), "with_gemini_rollouts": len(g), "with_ge1_success": len(succ), "reference_solutions_nonempty": nonempty_ref,
            "container_def_with_gpfs_paths": gp, "post_with_network_commands": net_post,
            "gemini_success_hist_of_8": dict(sorted(Counter(v[0] for v in dist.values()).items()))}


def main() -> None:
    rows = A.sample()
    res = {r["key"]: screen(r) for r in rows}
    out = {"per_task": res, "tmax_corpus": tmax_corpus()}
    json.dump(out, open(A.OUT / "static_screen.json", "w"), indent=1)
    print(json.dumps(out["tmax_corpus"]))
    for k, v in res.items():
        print(k[:60].ljust(60), "expo:", v["n_exposure_literal_hits"], "/", v["n_test_literals"], "named:", len(v["exposure_named_files"]),
              "net_rt:", v["runtime_network_in_reference_or_tests"][:3], "wrap:", len(v["wrapper_fetches"]), "gpu:", v["gpu"], "priv:", v["privilege"][:2], "dng:", v["danger"][:2])


if __name__ == "__main__":
    main()
