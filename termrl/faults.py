"""Deterministic, recoverable environment faults.

Each fault is injected as root after the container starts and before the agent's first
turn, on an *input* the task genuinely reads (a file present in the initial image and
named in the instruction). Every fault is repairable by the agent with ordinary user
permissions, and every family has a generic repair script used only to prove, per task,
that a correct recovery exists (reference solution run after the repair must pass).

Families:
  perm_denied   input chowned to the agent and made unreadable (repair: chmod u+r)
  moved_input   input moved to a hidden sibling directory (repair: find it, move it back)
  missing_tool  a CLI tool the reference solution uses is removed (repair: use an alternative)
  blocking_fifo input replaced by a FIFO that no one writes; the bytes survive in a backup
                next to it (repair: notice the hang, use the backup). Held out from training.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
from dataclasses import dataclass

from .sandbox import Sandbox, docker
from .tasks import Task

TRAIN_FAMILIES = ("perm_denied", "moved_input", "missing_tool")
HELDOUT_FAMILIES = ("blocking_fifo",)
TOOLS = ("jq", "rsync", "gawk", "sqlite3", "csvtool", "bc", "column", "sort", "uniq", "awk")


@dataclass
class Fault:
    family: str
    target: str  # file path, or tool name for missing_tool
    detail: str = ""

    def as_dict(self) -> dict:
        return {"family": self.family, "target": self.target, "detail": self.detail}


def _h(*parts) -> int:
    return int(hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()[:12], 16)


def initial_files(task: Task) -> list[str]:
    """Regular files under /home/user in the pristine task image (cached next to the task)."""
    cache_dir = os.environ.get("TERMRL_CACHE", "/mnt/sdb/arafat/ehz/llm/.pools/.cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache = os.path.join(cache_dir, f"{task.task_id}.{task.env_hash()}.files")
    if os.path.exists(cache):
        return [l for l in open(cache).read().splitlines() if l]
    out = docker(["run", "--rm", "--network", "none", "--entrypoint", "find", task.ensure_image(),
                  "/home/user", "-type", "f"], timeout=120).stdout.decode().split()
    with open(cache, "w") as f:
        f.write("\n".join(out) + "\n")
    return out


def input_candidates(task: Task) -> list[str]:
    text = task.instruction
    cands = []
    for p in initial_files(task):
        base = os.path.basename(p)
        if p in text or re.search(r"(?<![\w.-])" + re.escape(base) + r"(?![\w-])", text):
            cands.append(p)
    return sorted(cands)


def tool_candidates(task: Task) -> list[str]:
    sol = task.solution or ""
    return [t for t in TOOLS if re.search(r"(?<![\w/-])" + re.escape(t) + r"(?![\w-])", sol) and t not in ("sort", "uniq", "awk")]


def choose(task: Task, family: str, seed: int) -> Fault | None:
    if family == "missing_tool":
        tools = tool_candidates(task)
        return Fault(family, tools[_h(task.task_id, family, seed) % len(tools)]) if tools else None
    files = input_candidates(task)
    if not files:
        return None
    return Fault(family, files[_h(task.task_id, family, seed) % len(files)])


def inject(sb: Sandbox, fault: Fault, seed: int) -> Fault:
    t = shlex.quote(fault.target)
    if fault.family == "perm_denied":
        sb.root_exec(f"chown 1000:1000 {t} && chmod 000 {t}")
    elif fault.family == "moved_input":
        hide = f"/home/user/.cache_{_h(fault.target, seed) % 10**6:06d}"
        sb.root_exec(f"mkdir -p {hide} && chown 1000:1000 {hide} && mv {t} {hide}/ && chown 1000:1000 {hide}/*")
        fault.detail = hide
    elif fault.family == "missing_tool":
        sb.root_exec(f"for p in $(command -v -a {t} 2>/dev/null) /usr/bin/{t} /bin/{t}; do rm -f \"$p\"; done")
    elif fault.family == "blocking_fifo":
        backup = fault.target + ".bak"
        b = shlex.quote(backup)
        sb.root_exec(f"mv {t} {b} && chown 1000:1000 {b} && mkfifo {t} && chown 1000:1000 {t} && chmod 666 {t}")
        fault.detail = backup
    else:
        raise ValueError(fault.family)
    return fault


def repair_script(fault: Fault) -> str:
    """A correct recovery, used only to validate that each (task, fault) pair is solvable."""
    t = shlex.quote(fault.target)
    if fault.family == "perm_denied":
        return f"chmod u+rw {t}"
    if fault.family == "moved_input":
        return f"mv {shlex.quote(fault.detail)}/{shlex.quote(os.path.basename(fault.target))} {t} && rmdir {shlex.quote(fault.detail)}"
    if fault.family == "blocking_fifo":
        return f"rm -f {t} && mv {shlex.quote(fault.detail)} {t}"
    return ""  # missing_tool: validity is established by an alternative solution, not a repair
