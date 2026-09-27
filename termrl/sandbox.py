"""Docker sandbox with a persistent bash session.

One container per trial, started from an immutable task image with networking off.
Commands run inside one long-lived `bash` so `cd`, variables and functions persist
across tool calls, the way a human terminal behaves. Each command is shipped
base64-encoded and `eval`ed, so unbalanced quotes or a stray heredoc produce a
syntax error instead of wedging the session, and stdin is `/dev/null` so a
command that waits for input returns instead of eating the next command.
"""

from __future__ import annotations

import base64
import os
import select
import secrets
import subprocess
import time
from dataclasses import dataclass

DOCKER = ["sg", "docker", "-c"]


def docker(args: list[str], *, timeout: float = 120, check: bool = True, input: bytes | None = None) -> subprocess.CompletedProcess:
    """Run a docker CLI command through `sg docker` (the user is not in the docker group by default)."""
    cmd = " ".join(_q(a) for a in ["docker", *args])
    proc = subprocess.run([*DOCKER, cmd], capture_output=True, timeout=timeout, input=input)
    if check and proc.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args[:3])} failed ({proc.returncode}): {proc.stderr.decode(errors='replace')[-2000:]}")
    return proc


def _q(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


@dataclass
class CommandResult:
    output: str
    exit_code: int | None  # None when the command timed out
    timed_out: bool
    truncated: bool
    seconds: float


def truncate(text: str, limit: int) -> tuple[str, bool]:
    """Keep the head and tail of long output, marking the cut, so errors at the end stay visible."""
    if len(text) <= limit:
        return text, False
    head = limit * 2 // 3
    tail = limit - head
    omitted = len(text) - head - tail
    return f"{text[:head]}\n[... {omitted} characters omitted ...]\n{text[-tail:]}", True


class Sandbox:
    """A running task container plus a persistent shell inside it."""

    def __init__(
        self,
        image: str,
        *,
        workdir: str = "/home/user",
        cpus: float = 1.0,
        memory: str = "2g",
        pids: int = 256,
        command_timeout: float = 30.0,
        output_limit: int = 6000,
        user: str = "1000:1000",
    ):
        self.image = image
        self.workdir = workdir
        self.user = user
        self.command_timeout = command_timeout
        self.output_limit = output_limit
        self.name = "w" + secrets.token_hex(6)
        docker([
            "run", "-d", "--name", self.name, "--label", f"termrl.owner_pid={os.getpid()}", "--network", "none",
            "--cpus", str(cpus), "--memory", memory, "--pids-limit", str(pids),
            "--security-opt", "no-new-privileges", "--cap-drop", "NET_RAW",
            "--workdir", workdir, "--entrypoint", "sleep", image, "infinity",
        ])
        self._shell: subprocess.Popen | None = None
        # The agent owns its home tree, as a real user would; system paths stay root-owned.
        docker(["exec", "-u", "0:0", self.name, "chown", "-R", self.user, workdir], timeout=60)
        self._start_shell()

    # -- shell management -------------------------------------------------
    def _start_shell(self) -> None:
        # The agent is an ordinary user, as in the Apptainer setup Endless Terminals was built for;
        # as root, permission faults would be meaningless and the whole filesystem writable.
        cmd = " ".join(["docker", "exec", "-i", "-u", self.user, "-w", _q(self.workdir), "-e", "TERM=dumb",
                        "-e", "PAGER=cat", "-e", "GIT_PAGER=cat", "-e", "HOME=/home/user", "-e", "USER=user",
                        self.name, "bash", "--noprofile", "--norc"])
        self._shell = subprocess.Popen([*DOCKER, cmd], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, bufsize=0)

    def _kill_container_processes(self) -> None:
        # PID 1 is `sleep infinity`; everything else (the shell and anything it spawned) goes.
        docker(["exec", self.name, "sh", "-c", "kill -9 -1"], check=False, timeout=30)
        if self._shell is not None:
            self._shell.kill()
            self._shell.wait(timeout=10)

    def root_exec(self, script: str, timeout: float = 60) -> subprocess.CompletedProcess:
        """Run a setup script as root, outside the agent's session (used for fault injection)."""
        return docker(["exec", "-u", "0:0", self.name, "bash", "-c", script], timeout=timeout)

    def run(self, command: str, timeout: float | None = None) -> CommandResult:
        timeout = self.command_timeout if timeout is None else timeout
        assert self._shell is not None and self._shell.stdin is not None and self._shell.stdout is not None
        nonce = secrets.token_hex(8)
        marker = f"__END_{nonce}__"
        payload = base64.b64encode(command.encode()).decode()
        line = f'eval "$(printf %s {payload} | base64 -d)" < /dev/null 2>&1; __rc=$?; echo; echo "{marker} $__rc"\n'
        t0 = time.monotonic()
        try:
            self._shell.stdin.write(line.encode())
            self._shell.stdin.flush()
        except BrokenPipeError:
            self._start_shell()
            return CommandResult("[shell had exited; a fresh shell was started in the working directory]", None, False, False, 0.0)
        buf = bytearray()
        fd = self._shell.stdout.fileno()
        deadline = t0 + timeout
        exit_code: int | None = None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            ready, _, _ = select.select([fd], [], [], min(remaining, 0.5))
            if not ready:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:  # shell exited (e.g. the command ran `exit`)
                break
            buf.extend(chunk)
            text = buf.decode(errors="replace")
            idx = text.rfind(marker)
            if idx != -1 and text.endswith("\n", idx):
                tail = text[idx + len(marker):].strip()
                exit_code = int(tail) if tail.lstrip("-").isdigit() else None
                output = text[:idx]
                if output.endswith("\n"):
                    output = output[:-1]
                out, cut = truncate(output, self.output_limit)
                return CommandResult(out, exit_code, False, cut, time.monotonic() - t0)
        elapsed = time.monotonic() - t0
        partial = buf.decode(errors="replace")
        exited = self._shell.poll() is not None
        self._kill_container_processes()
        self._start_shell()
        out, cut = truncate(partial, self.output_limit)
        if exited and elapsed < timeout:
            note = "[the shell exited; a fresh shell was started in the working directory]"
            return CommandResult((out + "\n" if out else "") + note, None, False, cut, elapsed)
        note = (f"[command timed out after {timeout:.0f}s and was killed; the shell was restarted in "
                f"{self.workdir}, so directory changes and shell variables were reset]")
        return CommandResult((out + "\n" if out else "") + note, None, True, cut, elapsed)

    # -- lifecycle ----------------------------------------------------------
    def commit(self) -> str:
        """Snapshot the container's filesystem as an image for out-of-sandbox verification."""
        tag = f"termrl-snap:{self.name}"
        docker(["commit", "--pause=true", self.name, tag], timeout=300)
        return tag

    def close(self) -> None:
        try:
            if self._shell is not None and self._shell.poll() is None:
                self._shell.kill()
        finally:
            docker(["rm", "-f", self.name], check=False, timeout=60)

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
