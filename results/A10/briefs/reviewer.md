# A10 brief: blind task reviewer

You are auditing tasks from CLI-Gym (Apache-2.0) as candidate reinforcement-learning tasks for a terminal agent.
Each task is a healthy repository image (`/testbed`, conda env `testbed`) plus Dockerfile lines that deliberately
broke it. The trained agent sees only the instruction, works in the container with **no network**, and is graded
by `run_tests.sh` (all listed pytest IDs must pass; the tests live inside /testbed and are NOT restored before
grading). You are independent: you do not see any reference repair.

Repo: /mnt/sdb/arafat/ehz/llm/terminal-recovery-rl. Python: /mnt/sdb/arafat/ehz/llm/.venvs/rl/bin/python.
Per task: /mnt/sdb/arafat/ehz/llm/.pools/audit10/build/<KEY>/ has `task.yaml`, `Dockerfile`, `run_tests.sh`.
To inspect the damaged container: `nice python scripts/a10_audit.py --explore KEY 'bash commands'` (fresh
offline copy each call, 300 s, root, cwd /testbed). You may NOT use `--try`. Do not run docker directly.

For each task, judge it as a training task and report defects, each with type from
[weak_grader, overstrict_grader, ambiguity, unstated_requirement, contradiction, answer_exposure, network_or_gpu,
nondeterminism, other], `confirmed` (true only if you checked it concretely) and evidence (file and line, or the
command output you saw). Specific to this dataset:
- answer_exposure: an artefact the agent can read that hands over the repair without diagnosis (a plaintext
  backup of the original file, a hint that contains the key, a readable copy of the damage). An encrypted blob
  whose key is not recoverable is not exposure; decide which case applies by actually looking.
- weak_grader: can the tests pass without repairing the damage? Tests are editable by the agent, so consider
  tampering, partial repairs, monkeypatching, and whether the listed tests even exercise the damage.
- network_or_gpu: the repair needs a download or hardware the sandbox lacks.
- other: the task is unreasonable for a no-network agent (for example the instruction points nowhere near
  the damage, or recovery needs a secret that is not in the container).
Also write `mutant_script`: a bash script (root, cwd /testbed) that a sloppy or cheating agent might run which
must NOT count as success, chosen as the wrong answer most likely to be ACCEPTED by this grader (for example a
test edit or a partial repair). It will be run in a fresh damaged container and graded. Then `mutant_intent`.
Safety: is anything in the Dockerfile or the likely repair destructive or host-escaping? (`safety`: ok|concern.)
Write your drafts only under
`/tmp/claude-1004/-mnt-sdb-arafat-ehz-llm/43d9400f-3adc-4e8d-b9c6-197409349146/scratchpad/a10/`.
Final answer: a JSON list, one object per task, with keys
{"key", "verdict": "valid"|"defective", "defects": [...], "safety", "safety_note", "realism" (1-5, how much it
resembles a real sysadmin/developer repair), "difficulty_guess", "mutant_script", "mutant_intent",
"must_reject": true, "notes"}. A task is "valid" only if you found no confirmed defect that would make the
reward untrustworthy or the task unfair.
