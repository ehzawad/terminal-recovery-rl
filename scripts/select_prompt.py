"""Choose arm P exactly as pre-registered (amendment A1).

dev_search tasks with a usable training-family fault are halved by sha256('psel:'+id).
Half A: all 8 frozen prompts x 1 trial. The two best by macro success (ties -> fewer mean
generated tokens) go to half B, each with and without check-and-revise, x 2 trials. The best of
those four configurations is P; the choice is written to runs/psel/choice.json.

Usage: python scripts/select_prompt.py
"""

import glob
import hashlib
import json
import os
import subprocess
import sys

OUT = "runs/psel"
PY = sys.executable


def rows_for(half: str, trials: int) -> str:
    path = f"{OUT}/rows_{half}.jsonl"
    subprocess.run([PY, "scripts/make_rows.py", "--partition", "dev_search", "--trials", str(trials),
                    "--families", "train", "--out", path + ".all"], check=True)
    keep = []
    for line in open(path + ".all"):
        r = json.loads(line)
        h = int(hashlib.sha256(f"psel:{r['task_id']}".encode()).hexdigest()[:8], 16) % 2
        if (h == 0) == (half == "A"):
            keep.append(line)
    with open(path, "w") as f:
        f.writelines(keep)
    os.remove(path + ".all")
    return path


def run(rows: str, name: str, prompt: str, revise: bool) -> dict:
    out = f"{OUT}/{name}.jsonl"
    cmd = [PY, "scripts/evaluate.py", "--rows", rows, "--out", out, "--system-prompt-file", prompt]
    if revise:
        cmd.append("--check-revise")
    subprocess.run(cmd, check=True)
    return json.load(open(out.replace(".jsonl", ".summary.json")))


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    rows_a = rows_for("A", 1)
    rows_b = rows_for("B", 2)
    prompts = sorted(glob.glob("prompts/p*.txt"))
    stage1 = {}
    for p in prompts:
        name = os.path.basename(p)[:-4]
        stage1[name] = run(rows_a, f"A_{name}", p, False)
        print(name, stage1[name]["success_macro"], flush=True)
    ranked = sorted(stage1, key=lambda n: (-stage1[n]["success_macro"], stage1[n]["gen_tokens_mean"]))
    stage2 = {}
    for name in ranked[:2]:
        for revise in (False, True):
            key = f"{name}{'+revise' if revise else ''}"
            stage2[key] = run(rows_b, f"B_{key}", f"prompts/{name}.txt", revise)
            print(key, stage2[key]["success_macro"], flush=True)
    best = sorted(stage2, key=lambda k: (-stage2[k]["success_macro"], stage2[k]["gen_tokens_mean"]))[0]
    choice = {"P": best, "prompt_file": f"prompts/{best.split('+')[0]}.txt", "check_revise": best.endswith("+revise"),
              "stage1": {k: {x: v[x] for x in ("success_macro", "partial_mean", "recovery_failure_incidence", "gen_tokens_mean")}
                         for k, v in stage1.items()},
              "stage2": {k: {x: v[x] for x in ("success_macro", "partial_mean", "recovery_failure_incidence", "gen_tokens_mean")}
                         for k, v in stage2.items()}}
    json.dump(choice, open(f"{OUT}/choice.json", "w"), indent=1)
    print(json.dumps(choice, indent=1))


if __name__ == "__main__":
    main()
