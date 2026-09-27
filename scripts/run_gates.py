"""Select arm P and run the pre-RL gates against one vLLM server, in the registered order.

  1. select_prompt.py                     -> runs/psel_v4/choice.json
  2. gates.py headline with P's prompt    -> runs/gates_v4/headline.json
  3. gates.py variance with P's prompt, only if step 2 names a headline and the headroom gate passes
     (gate 2 failing stops the study before R: "prompting suffices")

Each finished step prints one 'STEP <name> ...' line and copies its record into results/. Needs frozen
contracts (data/contracts_v4_frozen.jsonl) and an idle A6000.

Usage: python scripts/run_gates.py > runs/gates_v4.log 2>&1
"""

import json
import os
import shutil
import subprocess
import sys

from termrl import server

PY = sys.executable


def main() -> None:
    if not os.path.exists("data/contracts_v4_frozen.jsonl"):
        sys.exit("data/contracts_v4_frozen.jsonl is missing: freeze the contracts first")
    proc = server.start(log_path="runs/vllm_gates_v4.log")
    try:
        subprocess.run([PY, "scripts/select_prompt.py"], check=True)
        choice = json.load(open("runs/psel_v4/choice.json"))
        shutil.copy("runs/psel_v4/choice.json", "results/psel_v4_choice.json")
        print(f"STEP psel P={choice['P']} prompt={choice['prompt_file']}", flush=True)

        subprocess.run([PY, "scripts/gates.py", "headline", "--prompt-file", choice["prompt_file"]], check=True)
        head = json.load(open("runs/gates_v4/headline.json"))
        shutil.copy("runs/gates_v4/headline.json", "results/gate_headline_v4.json")
        print(f"STEP headline headline={head['headline']} headroom={head['headroom_gate_pass']} "
              f"P_safe={head['P_safe_success_macro']} recovery_failure={head['recovery_failure_incidence']} "
              f"collateral={head['collateral_incidence_clean']}", flush=True)
        if head["stop_prompting_suffices"] or not head["headroom_gate_pass"]:
            print("STEP stop gate 2 failed: the study stops before R", flush=True)
            return

        subprocess.run([PY, "scripts/gates.py", "variance", "--prompt-file", choice["prompt_file"]], check=True)
        var = json.load(open("runs/gates_v4/variance.json"))
        shutil.copy("runs/gates_v4/variance.json", "results/gate_variance_v4.json")
        print(f"STEP variance pass={var['variance_gate_pass']} wilson95_lower={var['wilson95_lower']} "
              f"mixed={var['mixed_safe_success_groups']}/{var['groups']}", flush=True)
    finally:
        server.stop(proc)
        print("STEP done", flush=True)


if __name__ == "__main__":
    main()
