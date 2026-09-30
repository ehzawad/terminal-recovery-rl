"""A12 runner: episodes + v1/v2 grading per task, processed one base image at a time (disk).

  a12_run.py --model teacher --split train --attempts 2 --out teacher_train
  a12_run.py --model teacher --split test  --attempts 4 --out teacher_test
  a12_run.py --model sft:/path/to/adapter --split test --attempts 4 --out sft_test

Per task: build; gold image must pass v1; the untouched damaged container must FAIL v2; then N episodes, each
graded by replaying its change set onto fresh containers (v1 and v2). Records: results/A12/<out>/<key>.json,
traces: results/A12/<out>/traces/<key>/<i>.json. Resumable.
"""
from __future__ import annotations

import argparse, concurrent.futures as cf, itertools, json, re, sys, textwrap, time
from pathlib import Path

import yaml
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import a10_audit as A10  # noqa: E402
import a11_grade as G  # noqa: E402
from termrl import cligym, server  # noqa: E402
from termrl.config import MODEL_PATH  # noqa: E402
from termrl.rollout import Renderer  # noqa: E402
from termrl.sandbox import docker  # noqa: E402

OUT = ROOT / "results/A12"
CS = A10.POOL / "a12_cs"
PROMPT = (ROOT / "prompts/p7_cligym_repair.txt").read_text().strip()
TEACHER = "Qwen/Qwen3.5-27B-FP8"


def instruction_of(task_yaml: str) -> str:
    """The task's `instruction:` block; falls back to a literal-block scan when the file is not valid YAML."""
    try:
        return yaml.safe_load(task_yaml)["instruction"].strip()
    except Exception:
        lines = task_yaml.splitlines()
        i = next(k for k, l in enumerate(lines) if l.startswith("instruction:"))
        body = []
        for l in lines[i + 1:]:
            if re.match(r"^[A-Za-z_]+:", l):
                break
            body.append(l)
        return textwrap.dedent("\n".join(body)).strip()


def tasks(split: str) -> list[dict]:
    if split == "train":
        return json.load(open(OUT / "train_tasks.json"))["tasks"]
    if split.endswith(".json"):
        return json.load(open(split))["tasks"]
    cand = {c["key"]: c for c in json.load(open(ROOT / "results/A11/candidates.json"))["ordered"]}
    return sorted((cand[k] for k in json.load(open(OUT / "test_tasks.json"))["tasks"]), key=lambda r: (r["base"], r["hash"]))


def run_task(row: dict, out: Path, attempts: int, client: OpenAI, renderer: Renderer, model: str) -> dict:
    rec = {"key": row["key"], "base": row["base"], "t0": time.strftime("%H:%M:%S")}
    spec = A10.spec_of(row)
    ok, msg = A10.build(spec)
    if not ok:
        return {**rec, "usable": False, "why": "build_fail: " + msg[-300:]}
    with A10.box(spec, gold=True) as b:
        g = A10.grade(b)
    if not g["pass"]:
        return {**rec, "usable": False, "why": f"gold_fail: {g.get('summary')}"}
    dmg = G.damage_set(spec)
    with A10.box(spec) as b:
        noop = G.grade_v2(b, dmg)
    if noop["pass"]:
        return {**rec, "usable": False, "why": "vacuous: untouched container passes v2"}
    instruction = instruction_of((Path(spec["ctx"]) / "task.yaml").read_text())
    tdir = out / "traces" / row["key"]
    tdir.mkdir(parents=True, exist_ok=True)

    def one(i: int) -> dict:
        cs = CS / out.name / row["key"] / str(i)
        tr = cligym.run_episode(client, renderer, model, spec["image"], instruction, str(cs), system_prompt=PROMPT,
                                seed=1000 * i + int(row["hash"][:6], 16) % 1000)
        (tdir / f"{i}.json").write_text(json.dumps(tr))
        res = {"i": i, "end": tr["end_reason"], "cmds": len(tr.get("commands", [])),
               "harness_error": bool(tr.get("harness_error") or tr.get("capture_error"))}
        if tr.get("change_set"):
            with A10.box(spec) as b:
                cligym.replay(b.name, str(cs))
                res["v1"] = A10.grade(b)["pass"]
            with A10.box(spec) as b:
                cligym.replay(b.name, str(cs))
                v2 = G.grade_v2(b, dmg)
                res["v2"], res["v2_detail"] = v2["pass"], {"bc": v2["bc"]["fails"][:5], "tests": v2["tests"]}
        return res

    with cf.ThreadPoolExecutor(attempts) as ex:
        eps = list(ex.map(one, range(attempts)))
    return {**rec, "usable": True, "image": spec["image"], "episodes": eps}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--split", required=True, help="train | test | path to a tasks json")
    ap.add_argument("--attempts", type=int, default=2)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tasks-parallel", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    out = Path(a.out) if "/" in a.out else OUT / a.out
    out.mkdir(parents=True, exist_ok=True)
    todo = [r for r in tasks(a.split) if not (out / f"{r['key']}.json").exists()]
    if a.limit:
        todo = todo[: a.limit]
    if a.model == "teacher":
        from huggingface_hub import snapshot_download
        proc = server.start(log_path=str(ROOT / f"runs/a12_{a.out}_vllm.log"), max_model_len=32768, max_num_seqs=16,
                            model_path=snapshot_download(TEACHER, local_files_only=True), served_name="teacher", gpu_util=0.90)
        model = "teacher"
    elif a.model.startswith("sft:"):
        proc = server.start(lora={"sft": a.model[4:]}, log_path=str(ROOT / f"runs/a12_{a.out}_vllm.log"),
                            max_model_len=32768, max_num_seqs=16)
        model = "sft"
    else:
        proc = server.start(log_path=str(ROOT / f"runs/a12_{a.out}_vllm.log"), max_model_len=32768, max_num_seqs=16)
        model = "q9"
    try:
        client = OpenAI(base_url=f"http://127.0.0.1:{server.PORT}/v1", api_key="x", timeout=1800)
        renderer = Renderer(MODEL_PATH)
        for base, grp in itertools.groupby(todo, key=lambda r: r["base"]):
            grp = list(grp)

            def work(r):
                try:
                    res = run_task(r, out, a.attempts, client, renderer, model)
                except Exception as e:
                    res = {"key": r["key"], "usable": False, "why": f"harness_error: {e!r}"[:400]}
                (out / f"{r['key']}.json").write_text(json.dumps(res, indent=1))
                eps = res.get("episodes") or []
                print(r["key"][8:70], res.get("why", "ok"), "v2", sum(bool(e.get("v2")) for e in eps), "/", len(eps), flush=True)
                return res

            with cf.ThreadPoolExecutor(a.tasks_parallel) as ex:
                results = list(ex.map(work, grp))
            imgs = sorted({x["image"] for x in results if x.get("image")} | {A10.spec_of(r)["image"] for r in grp} | {base})
            docker(["image", "rm", "-f", *imgs], check=False, timeout=600)
    finally:
        server.stop(proc)


if __name__ == "__main__":
    main()
