"""Evaluate several arms on the same rows with P's frozen prompt (checkpoint selection or final test).

Each arm is NAME=base (the instruct model) or NAME=<adapter dir>. Adapters are served two at a time
next to the base model (vLLM --max-loras 2); every arm sees the identical rows, prompt, decoding
and harness. Outputs: <out>/<NAME>.jsonl plus a summary per arm.

Usage:
  python scripts/run_eval_arms.py --rows data/rows/test_faulted.jsonl --out runs/eval/test \
      --prompt-file prompts/p3_termination.txt --arm P=base --arm S=runs/S_seed1/r2/epoch2 ...
"""

import argparse
import os
import subprocess
import sys

from termrl import server

PY = sys.executable


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--arm", action="append", required=True)
    ap.add_argument("--check-revise", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    arms = [a.split("=", 1) for a in args.arm]
    adapters = [(n, p) for n, p in arms if p != "base"]
    batches = [adapters[i:i + 2] for i in range(0, len(adapters), 2)] or [[]]
    base_done = False
    for batch in batches:
        proc = server.start(dict(batch) if batch else None, log_path=f"{args.out}/vllm.log")
        try:
            todo = list(batch)
            if not base_done and any(p == "base" for _, p in arms):
                todo = [(n, "base") for n, p in arms if p == "base"] + todo
                base_done = True
            for name, path in todo:
                cmd = [PY, "scripts/evaluate.py", "--rows", args.rows, "--out", f"{args.out}/{name}.jsonl",
                       "--model", "q9" if path == "base" else name, "--system-prompt-file", args.prompt_file,
                       "--concurrency", "6"]
                if args.check_revise:
                    cmd.append("--check-revise")
                subprocess.run(cmd, check=True)
        finally:
            server.stop(proc)


if __name__ == "__main__":
    main()
