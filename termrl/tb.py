"""Terminal-Bench-style tasks (TBLite / Harbor layout) in an offline sandbox with the benchmark's own grading.

A task directory holds instruction.md, task.toml, environment/Dockerfile (build context environment/),
tests/test.sh (+ test files) and solution/solve.sh. Differences from the Endless Terminals path:

- the container keeps the image's user (root unless the Dockerfile says otherwise) and WORKDIR; nothing is
  chowned; a start-up service named by the image's ENTRYPOINT/CMD (anything but a bare shell) is started in
  the background, and the container is kept alive with `sleep infinity`;
- network is off for the agent and for grading (images are built with network beforehand);
- the shell runs as its own session, and a timed-out command kills only that session, so services the agent
  detached keep running;
- grading happens in the same container after the agent's session is stopped, as the benchmark does:
  tests/ is copied to /tests, /logs/verifier is emptied, `bash /tests/test.sh` runs in WORKDIR, and the score
  is the native reward the grader writes to /logs/verifier/reward.txt (fractional credit is kept; a missing or
  malformed reward scores 0 and is flagged). pytest's exit status is recorded but is not the score: some
  TBLite wrappers pass pytest whatever the task score.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
import tomllib
from dataclasses import dataclass, field

from .sandbox import DOCKER, Sandbox, _killpg, _q, docker

DEFAULT_CPUS, DEFAULT_MEMORY_MB = 2, 4096
MAX_CPUS, MAX_MEMORY_MB = 4, 8192
SHELLS = {"bash", "/bin/bash", "sh", "/bin/sh", "/usr/bin/bash"}


@dataclass
class TBTask:
    name: str
    root: str
    instruction: str
    workdir: str
    service: str | None
    user: str | None
    cpus: float
    memory_mb: int
    agent_timeout: float
    verifier_timeout: float
    toml: dict = field(default_factory=dict)

    @property
    def env_dir(self) -> str:
        return os.path.join(self.root, "environment")

    def env_hash(self) -> str:
        h = hashlib.sha256()
        for dp, dn, fn in os.walk(self.env_dir):
            dn.sort()
            for f in sorted(fn):
                if f.endswith(".pyc"):
                    continue
                p = os.path.join(dp, f)
                h.update(os.path.relpath(p, self.env_dir).encode())
                h.update(open(p, "rb").read())
        return h.hexdigest()[:16]

    @property
    def image(self) -> str:
        return f"termrl-tb:{re.sub(r'[^a-z0-9_.-]', '-', self.name.lower())}-{self.env_hash()}"

    def ensure_image(self, timeout: float = 1800) -> str:
        if docker(["image", "inspect", self.image], check=False, timeout=60).returncode != 0:
            docker(["build", "-q", "-t", self.image, self.env_dir], timeout=timeout)
        return self.image


def _json_list(text: str) -> list[str] | None:
    try:
        v = json.loads(text)
        return v if isinstance(v, list) else None
    except json.JSONDecodeError:
        return None


def load_tb_task(root: str) -> TBTask:
    root = os.path.abspath(root)
    toml = tomllib.load(open(os.path.join(root, "task.toml"), "rb"))
    env = toml.get("environment", {})
    df = open(os.path.join(root, "environment", "Dockerfile")).read()
    wd = re.findall(r"^\s*WORKDIR\s+(\S+)", df, re.M)
    users = re.findall(r"^\s*USER\s+(\S+)", df, re.M)
    ent = re.findall(r"^\s*ENTRYPOINT\s+(.+)$", df, re.M)
    cmd = re.findall(r"^\s*CMD\s+(.+)$", df, re.M)
    def split(x: str) -> list[str]:
        v = _json_list(x)
        return v if v is not None else x.split()

    parts = [p for p in (split(ent[-1]) if ent else []) + (split(cmd[-1]) if cmd else []) if p]
    keepalive = parts[:3] == ["tail", "-f", "/dev/null"] or "sleep infinity" in " ".join(parts)
    service = None
    if parts and not (len(parts) == 1 and parts[0] in SHELLS) and not keepalive:
        service = " ".join(shlex.quote(p) for p in parts)
    cpus = min(float(env.get("cpus") or DEFAULT_CPUS), MAX_CPUS)
    mem = min(int(env.get("memory_mb") or DEFAULT_MEMORY_MB), MAX_MEMORY_MB)
    return TBTask(name=os.path.basename(root), root=root, instruction=open(os.path.join(root, "instruction.md")).read().strip(),
                  workdir=wd[-1] if wd else "/", service=service, user=users[-1] if users else None, cpus=cpus,
                  memory_mb=mem, agent_timeout=float(toml.get("agent", {}).get("timeout_sec", 900)),
                  verifier_timeout=float(toml.get("verifier", {}).get("timeout_sec", 900)), toml=toml)


class TBSandbox(Sandbox):
    """A Terminal-Bench task container (offline) with a persistent shell in the task's own WORKDIR."""

    def __init__(self, task: TBTask, *, command_timeout: float = 300.0, output_limit: int = 6000, pids: int = 1024):
        self.image = task.ensure_image()
        self.workdir = task.workdir
        self.user = task.user or "0:0"
        self.command_timeout = command_timeout
        self.output_limit = output_limit
        self.name = "t" + hashlib.sha256(os.urandom(16)).hexdigest()[:12]
        self._shell: subprocess.Popen | None = None
        self._sid: int | None = None
        keepalive = (f"({task.service}) >/tmp/.service.log 2>&1 & " if task.service else "") + "exec sleep infinity"
        mem = f"{task.memory_mb}m"
        docker(["run", "-d", "--name", self.name, "--label", f"termrl.owner_pid={os.getpid()}", "--network", "none",
                "--cpus", str(task.cpus), "--memory", mem, "--memory-swap", mem, "--pids-limit", str(pids),
                "--cap-drop", "NET_RAW", "--workdir", task.workdir, "--entrypoint", "/bin/sh", self.image, "-c", keepalive])
        try:
            self._start_shell()
        except BaseException:
            self.close()
            raise

    def _start_shell(self) -> None:
        cmd = " ".join(["docker", "exec", "-i", "-u", _q(self.user), "-w", _q(self.workdir), "-e", "TERM=dumb",
                        "-e", "PAGER=cat", "-e", "GIT_PAGER=cat", self.name, "setsid", "bash", "--noprofile", "--norc"])
        self._shell = subprocess.Popen([*DOCKER, cmd], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, bufsize=0, start_new_session=True)
        self._sid = None
        r = Sandbox.run(self, "echo $$", timeout=30)
        m = re.search(r"(\d+)", r.output or "")
        self._sid = int(m.group(1)) if m else None

    def _kill_container_processes(self) -> None:
        """Stop the agent's shell session only; services the agent detached into their own session survive."""
        if self._shell is not None:
            for f in (self._shell.stdin, self._shell.stdout):
                try:
                    f.close()
                except Exception:
                    pass
            _killpg(self._shell)
            try:
                self._shell.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        if self._sid:
            # /proc only (slim images have no ps/awk): field 4 after the ") " of /proc/PID/stat is the session id.
            script = ("for d in /proc/[0-9]*; do read -r l < $d/stat 2>/dev/null || continue; set -- ${l##*) }; "
                      f'[ "$4" = "{self._sid}" ] && kill -9 ${{d#/proc/}} 2>/dev/null; done; true')
            docker(["exec", "-u", "0:0", self.name, "sh", "-c", script], check=False, timeout=30)

    def stop_agent(self) -> None:
        """End the agent's session before grading (its detached services keep running)."""
        self._kill_container_processes()
        self._shell = None


@dataclass
class TBVerdict:
    reward: float
    success: bool
    pytest_rc: int | None
    error: str | None
    seconds: float
    log_tail: str


def grade(sb: TBSandbox, task: TBTask, timeout: float | None = None) -> TBVerdict:
    """The benchmark's own grader, in the task container, offline; score = native reward.txt."""
    t0 = time.monotonic()
    timeout = min(timeout or task.verifier_timeout, task.verifier_timeout)
    sb.stop_agent()
    docker(["exec", "-u", "0:0", sb.name, "sh", "-c", "rm -rf /tests /logs/verifier && mkdir -p /tests /logs/verifier"],
           check=False, timeout=60)
    with tempfile.TemporaryDirectory() as tmp:
        tar = os.path.join(tmp, "tests.tar")
        subprocess.run(["tar", "-C", os.path.join(task.root, "tests"), "--exclude", "__pycache__", "-cf", tar, "."], check=True)
        docker(["cp", tar, f"{sb.name}:/tmp/.tests.tar"], timeout=120)
    docker(["exec", "-u", "0:0", sb.name, "sh", "-c", "tar -C /tests -xf /tmp/.tests.tar && rm -f /tmp/.tests.tar"], timeout=120)
    try:
        r = docker(["exec", "-u", "0:0", "-w", task.workdir, sb.name, "bash", "/tests/test.sh"], check=False, timeout=timeout)
        rc, log, err = r.returncode, (r.stdout or b"").decode(errors="replace"), None
    except subprocess.TimeoutExpired:
        rc, log, err = None, "", f"grader exceeded {timeout:.0f}s"
    got = docker(["exec", "-u", "0:0", sb.name, "cat", "/logs/verifier/reward.txt"], check=False, timeout=60)
    text = (got.stdout or b"").decode(errors="replace").strip()
    try:
        reward = float(text)
        if not 0.0 <= reward <= 1.0:
            raise ValueError(text)
    except ValueError:
        reward, err = 0.0, err or f"missing or malformed reward: {text[:80]!r}"
    return TBVerdict(reward=reward, success=reward >= 1.0 - 1e-9 and err is None, pytest_rc=rc, error=err,
                     seconds=round(time.monotonic() - t0, 1), log_tail=log[-2000:])
