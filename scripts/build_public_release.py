"""Assemble the public Hugging Face snapshot from this repository (run from the repo root): python scripts/build_public_release.py OUT_DIR."""

import json
import os
import re
import shutil
import sys

SRC = os.getcwd()
DST = sys.argv[1]
if os.path.exists(DST):
    shutil.rmtree(DST)
os.makedirs(DST)

CORE = ["__init__.py", "config.py", "env.py", "faults.py", "fixtures.py", "manifest.py", "rollout.py", "sandbox.py",
        "server.py", "tasks.py", "tb.py", "verify.py"]
SCRIPTS = {"make_rows.py": "make_rows.py", "evaluate.py": "evaluate.py", "run_eval_arms.py": "run_eval_arms.py",
           "validate_tasks.py": "validate_tasks.py", "freeze_contracts.py": "freeze_contracts.py",
           "check_harness_v5.py": "check_harness.py", "smoke_sandbox.py": "smoke_sandbox.py",
           "cleanup_orphans.py": "cleanup_orphans.py", "train_grpo.py": "train_grpo.py", "train_sft.py": "train_sft.py",
           "adapter_parity.py": "adapter_parity.py", "tb_admission.py": "tb_admission.py",
           "probe_longctx.py": "probe_longctx.py"}

# (file, old, new): exact replacements; every one must apply.
EDITS = [
    ("termrl/config.py", " (A7).\"\"\"", ".\"\"\""),
    ("termrl/env.py", "RL (harness v5).", "RL."),
    ("termrl/env.py", "when a budget is set, A7: later calls are not", "when a budget is set; later calls are not"),
    ("termrl/env.py", "Reward (A2): -1", "Reward: -1"),
    ("termrl/env.py", "before any thread can see them (the v3 race).", "before any thread can see them."),
    ("termrl/env.py", 'f"no v4 contract for', 'f"no contract for'),
    ("termrl/env.py", '"contracts_v4_frozen.jsonl"', '"contracts.jsonl"'),
    ("termrl/faults.py", "Frozen rubric (amendment A5): the", "Frozen rubric: the"),
    ("termrl/manifest.py", "still `deleted` (A7).", "still `deleted`."),
    ("termrl/rollout.py", "With `max_commands` (A7) the", "With `max_commands` the"),
    ("termrl/rollout.py", '"harness": "v5"}', '"harness": "termrl-1"}'),
    ("termrl/tasks.py", "are excluded (amendment A6):", "are excluded:"),
    ("termrl/verify.py", "scores it as a failure (A2)", "scores it as a failure"),
    ("scripts/make_rows.py", "from the v4 validity gate and the frozen split (amendment A5).", "from the validity records and the frozen split."),
    ("scripts/make_rows.py", " (A1 for P selection).", "."),
    ("scripts/make_rows.py", "data/study2_partitions.json:gate", "data/partitions.json:gate"),
    ("scripts/make_rows.py", "`--max-commands N` (A7) writes", "`--max-commands N` writes"),
    ("scripts/make_rows.py", '"(default: data/validity/v4.jsonl then data/validity/v41.jsonl)")', '"(default: data/validity.jsonl)")'),
    ("scripts/make_rows.py", '["data/validity/v4.jsonl", "data/validity/v41.jsonl"]', '["data/validity.jsonl"]'),
    ("scripts/make_rows.py", '"data/splits_v1.json"', '"data/splits.json"'),
    ("scripts/make_rows.py", "(A7)\")", "\")"),
    ("scripts/make_rows.py", "  # A6: hidden tests that run or import code are excluded everywhere", "  # hidden tests that run or import code are excluded everywhere"),
    ("scripts/evaluate.py", "reports every registered quantity", "reports every quantity"),
    ("scripts/evaluate.py", "# A7 H: used every budgeted", "# used every budgeted"),
    ("scripts/evaluate.py", '"harness": "v5"}', '"harness": "termrl-1"}'),
    ("scripts/validate_tasks.py", "contract builder for harness v4 (pre-registration amendment A5).", "contract builder."),
    ("scripts/validate_tasks.py", "--ids data/validity/v1_order.txt --out data/validity/v4.jsonl \\\n      --contracts data/contracts_v4.jsonl --workers 8",
     "--ids ids.txt --out validity.jsonl \\\n      --contracts contracts_draft.jsonl --workers 8"),
    ("scripts/validate_tasks.py", '"harness": "v4.1"', '"harness": "termrl-1"'),
    ("scripts/freeze_contracts.py", "validity records (amendment A6).", "validity records."),
    ("scripts/freeze_contracts.py", "--validity data/validity/v4.jsonl [--validity more.jsonl] \\\n           --out data/contracts_v4_frozen.jsonl",
     "--validity validity.jsonl [--validity more.jsonl] \\\n           --out data/contracts.jsonl"),
    ("scripts/check_harness.py", "Checks for the harness-v5 changes (amendment A7), run before any Study 2 data.",
     "Checks of the command budget and the transition-aware safety oracle."),
    ("scripts/check_harness.py", "  replay        the two audited model episodes (mv, then ln -s)      -> no collateral, success",
     "  replay        two recorded model episodes (mv, then ln -s)         -> no collateral, success"),
    ("scripts/check_harness.py", "Usage: python scripts/check_harness_v5.py > results/harness_v5_checks.json",
     "Usage: python scripts/check_harness.py > results/harness_checks.json"),
    ("scripts/train_grpo.py", "Registered limits (A2, A5): at most", "Limits: at most"),
    ("scripts/train_grpo.py", "Registered stop rules (gate 4, windows fixed in A5), with", "Stop rules, with"),
    ("scripts/train_grpo.py", "the same command budget (A7), which", "the same command budget, which"),
    ("scripts/train_grpo.py", "  # A2: at most 64 updates x 16 trajectories", "  # at most 64 updates x 16 trajectories"),
    ("scripts/train_grpo.py", "  # A2: R's GPU-hour cap", "  # GPU-hour cap"),
    ("scripts/train_sft.py", "# Safe successes only (A2), never truncated or harness-error trajectories (A5).",
     "# Safe successes only, never truncated or harness-error trajectories."),
    ("scripts/smoke_sandbox.py", "Harness gate on real tasks:", "Harness check on real tasks:"),
]

os.makedirs(f"{DST}/termrl")
for f in CORE:
    shutil.copy(f"{SRC}/termrl/{f}", f"{DST}/termrl/{f}")
os.makedirs(f"{DST}/scripts")
for a, b in SCRIPTS.items():
    shutil.copy(f"{SRC}/scripts/{a}", f"{DST}/scripts/{b}")

# check_harness: replay commands ship as data instead of reading private run logs
p = f"{DST}/scripts/check_harness.py"
s = open(p).read()
old = '''    for line in open("runs/gates_v4/headline_P.jsonl"):
        t = json.loads(line)
        if t["task_id"] == "task_000000_4fee1147" and t.get("collateral") is not None:
            cmds = [tc["arguments"]["command"] for x in t["turns"] for tc in (x.get("tool_calls") or [])]
            replays.append({"row_id": t["row_id"], "calls": len(cmds), **run(t["task_id"], cmds)})'''
new = '''    for rec in json.load(open("data/checks/replay_4fee1147.json")):
        cmds = rec["commands"]
        replays.append({"episode": rec["episode"], "calls": len(cmds), **run("task_000000_4fee1147", cmds)})'''
assert old in s
open(p, "w").write(s.replace(old, new))

for f, a, b in EDITS:
    p = f"{DST}/{f}"
    s = open(p).read()
    if a not in s:
        sys.exit(f"edit did not apply: {f}: {a[:60]!r}")
    open(p, "w").write(s.replace(a, b))

# data
os.makedirs(f"{DST}/data/checks")
shutil.copy(f"{SRC}/data/contracts_v4_frozen.jsonl", f"{DST}/data/contracts.jsonl")
audited = set(json.load(open(f"{SRC}/data/audit/endless_recommended_ids.json")))
recs = {}
for path in ("data/validity/v4.jsonl", "data/validity/v41.jsonl"):
    for line in open(f"{SRC}/{path}"):
        r = json.loads(line)
        if r["task_id"] in audited:
            recs[r["task_id"]] = r
with open(f"{DST}/data/validity.jsonl", "w") as fh:
    for tid in sorted(recs):
        r = dict(recs[tid])
        r["harness"] = "termrl-1"
        line = json.dumps(r)
        line = re.sub(r"/mnt/sdb/[^\"\\\\ ]*terminal-recovery-rl", "<repo>", line)
        assert "/mnt/sdb" not in line and "arafat" not in line, tid
        fh.write(line + "\n")
with open(f"{DST}/data/contracts.jsonl") as fh:
    lines = [json.loads(l) for l in fh]
with open(f"{DST}/data/contracts.jsonl", "w") as fh:
    for c in lines:
        c["harness"] = "termrl-1"
        fh.write(json.dumps(c) + "\n")
sp = json.load(open(f"{SRC}/data/splits_v1.json"))
json.dump({"rule": "sha256('termrl-split-v1:' + task_id) mod 16: 0-7 train, 8-9 dev_search, 10-11 dev_monitor, "
                   "12-15 test; 9 tasks used in the first harness probe are placed in dev_search. Fixed before any "
                   "model run on the other tasks. Unit = Endless Terminals task id.",
           "assignments": sp["assignments"]}, open(f"{DST}/data/splits.json", "w"), indent=1)
parts = json.load(open(f"{SRC}/data/study2_partitions.json"))
parts["note"] = "Task lists used by the command-budget evaluation (admitted = frozen contract and no code-executing hidden tests)"
json.dump(parts, open(f"{DST}/data/partitions.json", "w"), indent=1)
json.dump(json.load(open(f"{SRC}/data/audit/endless_recommended_ids.json")), open(f"{DST}/data/task_ids.json", "w"), indent=1)
replays = []
for line in open(f"{SRC}/runs/gates_v4/headline_P.jsonl"):
    t = json.loads(line)
    if t["task_id"] == "task_000000_4fee1147" and t.get("collateral") is not None:
        replays.append({"episode": len(replays), "commands": [tc["arguments"]["command"] for x in t["turns"]
                                                              for tc in (x.get("tool_calls") or [])]})
json.dump(replays, open(f"{DST}/data/checks/replay_4fee1147.json", "w"), indent=1)

# hard-task audit (tasks a strong model solved in only 1-11 of 16 attempts)
os.makedirs(f"{DST}/data/hard/review")
cands = json.load(open(f"{SRC}/data/hard/candidates.json"))
cands["rule"] = ("Endless Terminals @26ecf784 tasks that o3 solved in 1-11 of 16 attempts and that pass the same static "
                 "screens as the main slice (local text/stdlib, real data transformation, no dynamic time, no literal "
                 "answers, no code-executing hidden tests, light dependencies): 173, minus 2 dropped for dependencies.")
json.dump(cands, open(f"{DST}/data/hard/candidates.json", "w"), indent=1)
for f in ("admission.json", "near_duplicate_pairs.json"):
    shutil.copy(f"{SRC}/data/hard/{f}", f"{DST}/data/hard/{f}")
for f in sorted(os.listdir(f"{SRC}/data/hard/review")):
    if f.endswith(".json"):
        shutil.copy(f"{SRC}/data/hard/review/{f}", f"{DST}/data/hard/review/{f}")
with open(f"{DST}/data/hard/validity.jsonl", "w") as fh:
    for line in open(f"{SRC}/data/hard/validity.jsonl"):
        r = json.loads(line)
        r["harness"] = "termrl-1"
        line = re.sub(r"/mnt/sdb/[^\"\\ ]*terminal-recovery-rl", "<repo>", json.dumps(r))
        assert "/mnt/sdb" not in line and "arafat" not in line
        fh.write(line + "\n")
os.makedirs(f"{DST}/results", exist_ok=True)
rd = open(f"{SRC}/results/transfer_readiness.md").read()
rd = rd.replace("# Transfer-study readiness audit (model-free; no Terminal-Bench outcome of any policy)",
                "# Terminal-Bench readiness audit (model-free; no Terminal-Bench outcome of any policy)")
rd = rd.replace("The council's transfer design needs at least 80 admitted, lineage-independent external task groups.",
                "A transfer comparison with a 48-task final split plus development and gate splits needs at least 80 "
                "admitted, lineage-independent external task groups.")
assert "council" not in rd.lower()
open(f"{DST}/results/terminal_bench_readiness.md", "w").write(rd)
shutil.copy(f"{SRC}/results/probe_longctx.json", f"{DST}/results/probe_longctx.json")

# prompts
os.makedirs(f"{DST}/prompts")
for f in sorted(os.listdir(f"{SRC}/prompts")):
    shutil.copy(f"{SRC}/prompts/{f}", f"{DST}/prompts/{f}")
print("ok", DST)
