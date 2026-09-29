# A10 brief: repair-reference author

You are auditing tasks from CLI-Gym (Apache-2.0), a dataset of "broken environment" tasks. Each task is a healthy
repository image (`/testbed`, conda env `testbed`) plus Dockerfile lines that deliberately broke it. The agent that
will eventually train on these tasks gets only the instruction and a shell with **no network**. Your job is to
prove each assigned task is repairable under those conditions by writing a **repair script** that makes the task's
listed tests pass. You may read everything, including the Dockerfile that did the damage; the reviewers are
separate and blind to you.

Repo: /mnt/sdb/arafat/ehz/llm/terminal-recovery-rl. Python: /mnt/sdb/arafat/ehz/llm/.venvs/rl/bin/python.
Per task, the files are in /mnt/sdb/arafat/ehz/llm/.pools/audit10/build/<KEY>/ : `task.yaml` (instruction),
`Dockerfile` (the damage), `run_tests.sh` (the grader; the listed pytest IDs must all pass).

Tools (run from the repo root, prefix with `nice`):
- `python scripts/a10_audit.py --explore KEY 'bash commands'` runs the commands as root in /testbed in a FRESH,
  offline copy of the damaged container (nothing persists between calls; 300 s limit). Use freely to investigate.
- `python scripts/a10_audit.py --try KEY /path/to/repair.sh` is a COUNTED attempt (at most 3 per task): runs your
  script offline in a fresh damaged container (900 s), then grades it, and prints the result. A pass is saved as
  the task's reference automatically.

Rules for the repair script:
- A genuine repair of what the damage broke. Never edit, delete, skip, or add tests, conftest files, pytest config
  or `run_tests.sh`, never hard-code expected outputs, never special-case the test process.
- It may use anything already inside the damaged container (backups, hint files, the conda package cache if
  present) and knowledge from the Dockerfile, but it must run offline on the container as it stands. Record honestly
  whether it depends on facts an agent could only get from the Dockerfile (`used_dockerfile_only_knowledge`).
  If the only possible repair needs a download, stop and report the task as infeasible offline.
- Bash, run as root, working directory /testbed, idempotent where practical.

Do not run docker directly, do not remove images, and do not touch files outside
`/tmp/claude-1004/-mnt-sdb-arafat-ehz-llm/43d9400f-3adc-4e8d-b9c6-197409349146/scratchpad/a10/` (write your drafts there).
Final answer: a JSON list, one object per task:
{"key", "passed": bool, "attempts_used": int, "repair_summary": "what the damage was and what the repair does",
 "used_dockerfile_only_knowledge": bool, "infeasible_offline": bool, "reason_if_not_passed": str}
