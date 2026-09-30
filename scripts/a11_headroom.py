"""A11 headroom run: prompted base Qwen3.5-9B on CLI-Gym candidates in registered order, 4 attempts per usable task.

Usable = the damaged image builds and the gold image passes the dataset's own grader (v1). Traces go to
results/A11/episodes/<key>/<i>.json, change sets to POOL/a11_cs/<key>/<i>/. Images are kept for grading.
Usage: a11_headroom.py --max-tasks N [--tasks-parallel 2]   (resumable: finished tasks are skipped)
"""
from __future__ import annotations

import argparse, concurrent.futures as cf, json, sys, time
from pathlib import Path

import yaml
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import a10_audit as A10  # noqa: E402
from termrl import cligym, server  # noqa: E402
from termrl.config import MODEL_PATH  # noqa: E402
from termrl.rollout import Renderer  # noqa: E402

OUT = ROOT / "results/A11"
CS = A10.POOL / "a11_cs"
ATTEMPTS = 4
PROMPT = (ROOT / "prompts/p7_cligym_repair.txt").read_text().strip()


def status() -> dict:
    p = OUT / "tasks.json"
    return json.loads(p.read_text()) if p.exists() else {}


def save_status(s: dict) -> None:
    (OUT / "tasks.json").write_text(json.dumps(s, indent=1))


def usable(row: dict) -> tuple[bool, str, dict]:
    spec = A10.spec_of(row)
    ok, msg = A10.build(spec)
    if not ok:
        return False, "build_fail: " + msg[-300:], spec
    with A10.box(spec, gold=True) as b:
        g = A10.grade(b)
    return (True, "ok", spec) if g["pass"] else (False, f"gold_fail: {g.get('summary')}", spec)


def run_task(row: dict, client: OpenAI, renderer: Renderer) -> dict:
    ok, why, spec = usable(row)
    if not ok:
        return {"usable": False, "why": why}
    instruction = yaml.safe_load((Path(spec["ctx"]) / "task.yaml").read_text())["instruction"].strip()
    d = OUT / "episodes" / row["key"]
    d.mkdir(parents=True, exist_ok=True)

    def one(i: int) -> dict:
        tr = cligym.run_episode(client, renderer, "q9", spec["image"], instruction, str(CS / row["key"] / str(i)),
                                system_prompt=PROMPT, seed=1000 * i + int(row["hash"][:6], 16) % 1000)
        (d / f"{i}.json").write_text(json.dumps(tr))
        return {"end": tr["end_reason"], "cmds": len(tr.get("commands", [])), "err": bool(tr.get("harness_error") or tr.get("capture_error"))}

    with cf.ThreadPoolExecutor(ATTEMPTS) as ex:
        eps = list(ex.map(one, range(ATTEMPTS)))
    return {"usable": True, "why": "ok", "image": spec["image"], "gold": spec["gold"], "episodes": eps}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-tasks", type=int, default=8)
    ap.add_argument("--tasks-parallel", type=int, default=2)
    a = ap.parse_args()
    cands = json.load(open(OUT / "candidates.json"))["ordered"]
    st = status()
    n_usable = sum(1 for v in st.values() if v.get("usable"))
    todo = [r for r in cands if r["key"] not in st]
    proc = server.start(log_path=str(ROOT / "runs/a11_vllm.log"), max_model_len=32768, max_num_seqs=16)
    try:
        client = OpenAI(base_url=f"http://127.0.0.1:{server.PORT}/v1", api_key="x", timeout=1800)
        renderer = Renderer(MODEL_PATH)
        with cf.ThreadPoolExecutor(a.tasks_parallel) as ex:
            running = {}
            it = iter(todo)
            while True:
                while len(running) < a.tasks_parallel and n_usable + len(running) < a.max_tasks:
                    r = next(it, None)
                    if r is None:
                        break
                    running[ex.submit(run_task, r, client, renderer)] = r
                if not running:
                    break
                done, _ = cf.wait(running, return_when=cf.FIRST_COMPLETED)
                for f in done:
                    r = running.pop(f)
                    try:
                        res = f.result()
                    except Exception as e:
                        res = {"usable": False, "why": f"harness_error: {e!r}"[:400]}
                    st[r["key"]] = {**res, "t": time.strftime("%H:%M:%S")}
                    save_status(st)
                    n_usable += bool(res.get("usable"))
                    print(r["key"][:70], res.get("why"), res.get("episodes"), flush=True)
    finally:
        server.stop(proc)


if __name__ == "__main__":
    main()
