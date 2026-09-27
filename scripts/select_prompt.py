"""Choose arm P exactly as pre-registered (amendments A1, A3, A5).

Valid dev_search tasks *with a usable training-family fault* (A1's eligibility, restored in A5) are
halved by sha256('psel:'+id); every episode carries the task's planted fixtures and a hash-chosen
half of the (task, configuration) episodes carry a training-family fault (A3). Half A: all 10 frozen prompts x 1 trial. The two best by macro *safe* complete
success (ties -> fewer mean generated tokens) go to half B, x 2 trials each,
without the check-and-revise controller (A6). The better of the two is P; the choice is written to
runs/psel_v4/choice.json.

Usage: python scripts/select_prompt.py
"""

import glob
import hashlib
import json
import os
import subprocess
import sys

OUT = "runs/psel_v4"
PY = sys.executable


def rows_for(half: str, trials: int) -> str:
    path = f"{OUT}/rows_{half}.jsonl"
    subprocess.run([PY, "scripts/make_rows.py", "--partition", "dev_search", "--families", "mix",
                    "--fault-share", "0.5", "--require-faultable", "--configs-per-task", str(trials),
                    "--attempts", "1", "--out", path + ".all"], check=True)
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
        print(name, stage1[name]["safe_success_macro"], flush=True)
    ranked = sorted(stage1, key=lambda n: (-stage1[n]["safe_success_macro"], stage1[n]["gen_tokens_mean"]))
    stage2 = {}
    for name in ranked[:2]:  # A6: finalists compared without the check-and-revise controller
        stage2[name] = run(rows_b, f"B_{name}", f"prompts/{name}.txt", False)
        print(name, stage2[name]["safe_success_macro"], flush=True)
    best = sorted(stage2, key=lambda k: (-stage2[k]["safe_success_macro"], stage2[k]["gen_tokens_mean"]))[0]
    choice = {"harness": "v4.1", "P": best, "prompt_file": f"prompts/{best.split('+')[0]}.txt", "check_revise": best.endswith("+revise"),
              "stage1": {k: {x: v[x] for x in ("safe_success_macro", "safe_success_faulted", "safe_success_clean", "collateral_clean",
                                 "recovery_failure_observed", "failure_assigned_fault", "gen_tokens_mean")}
                         for k, v in stage1.items()},
              "stage2": {k: {x: v[x] for x in ("safe_success_macro", "safe_success_faulted", "safe_success_clean", "collateral_clean",
                                 "recovery_failure_observed", "failure_assigned_fault", "gen_tokens_mean")}
                         for k, v in stage2.items()}}
    json.dump(choice, open(f"{OUT}/choice.json", "w"), indent=1)
    print(json.dumps(choice, indent=1))


if __name__ == "__main__":
    main()
