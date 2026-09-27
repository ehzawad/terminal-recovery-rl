"""Choose one trained arm's checkpoint on dev_monitor and freeze the choice (amendments A5, A6).

Candidates are evaluated with P's prompt on dev_monitor episodes of the headline's type (2 configurations per
task, 1 attempt, salt 'ckpt-v4'); the highest macro safe success wins, ties go to the earlier candidate. The
choice is written once to results/selection_<arm>.json with sha256 identities of every candidate adapter, so
the adapter evaluated on test can be checked against it. Refuses to overwrite an existing selection.

Usage: python scripts/select_checkpoint.py --arm S --headline recovery_failure --prompt-file prompts/pX.txt \
           --candidate runs/S_seed1/r1/epoch1 --candidate runs/S_seed1/r1/epoch2 ...
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys

PY = sys.executable


def adapter_sha(path: str) -> str:
    h = hashlib.sha256()
    for name in sorted(os.listdir(path)):
        if name.endswith((".safetensors", ".json")):
            h.update(name.encode())
            h.update(open(os.path.join(path, name), "rb").read())
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--headline", choices=["recovery_failure", "collateral"], required=True)
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--candidate", action="append", required=True)
    args = ap.parse_args()
    out_path = f"results/selection_{args.arm}.json"
    if os.path.exists(out_path):
        sys.exit(f"{out_path} exists: this arm's checkpoint is already selected")
    rows = f"runs/ckpt_{args.arm}/rows.jsonl"
    os.makedirs(os.path.dirname(rows), exist_ok=True)
    subprocess.run([PY, "scripts/make_rows.py", "--partition", "dev_monitor",
                    "--families", "train" if args.headline == "recovery_failure" else "clean",
                    "--configs-per-task", "2", "--attempts", "1", "--salt", "ckpt-v4", "--out", rows], check=True)
    names = [f"{args.arm.lower()}{i}" for i in range(len(args.candidate))]
    arms = [f"{n}={p}" for n, p in zip(names, args.candidate)]
    subprocess.run([PY, "scripts/run_eval_arms.py", "--rows", rows, "--out", f"runs/ckpt_{args.arm}",
                    "--prompt-file", args.prompt_file, *sum((["--arm", a] for a in arms), [])], check=True)
    scores = []
    for i, (n, p) in enumerate(zip(names, args.candidate)):
        summ = json.load(open(f"runs/ckpt_{args.arm}/{n}.summary.json"))
        scores.append({"candidate": p, "order": i, "safe_success_macro": summ["safe_success_macro"],
                       "adapter_sha256": adapter_sha(p), "summary": summ})
    best = sorted(scores, key=lambda x: (-x["safe_success_macro"], x["order"]))[0]
    record = {"arm": args.arm, "headline": args.headline, "prompt_file": args.prompt_file,
              "rows_sha256": hashlib.sha256(open(rows, "rb").read()).hexdigest(),
              "chosen": best["candidate"], "chosen_adapter_sha256": best["adapter_sha256"],
              "candidates": [{k: v for k, v in s.items() if k != "summary"} for s in scores]}
    with open(out_path, "w") as f:
        json.dump(record, f, indent=1)
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
