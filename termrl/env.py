"""The terminal environment, shared by evaluation and RL.

TRL's `environment_factory` turns every public method except `reset`/`get_reward` into a
tool, so the evaluation client derives its tool schema from the very same `bash` method.
One definition means the policy sees an identical tool contract in both paths.
"""

from __future__ import annotations

import time

from . import faults
from .sandbox import Sandbox, docker
from .tasks import Task, load_task
from .verify import Verdict, verify_image


class TerminalEnv:
    def __init__(self, pool_dir: str | None = None, *, command_timeout: float = 30.0, output_limit: int = 6000):
        self._pool_dir = pool_dir
        self._command_timeout = command_timeout
        self._output_limit = output_limit
        self._sandbox: Sandbox | None = None
        self._task: Task | None = None
        self._log: list[dict] = []
        self._verdict: Verdict | None = None

    # TRL passes each dataset row's fields as keyword arguments.
    def reset(self, task_root: str | None = None, task_id: str | None = None, fault_family: str | None = None,
              fault_seed: int = 0, **_) -> None:
        self._teardown()
        root = task_root or f"{self._pool_dir}/{task_id}"
        self._task = load_task(root)
        image = self._task.ensure_image()
        self._sandbox = Sandbox(image, command_timeout=self._command_timeout, output_limit=self._output_limit)
        self._log = []
        self._verdict = None
        self._fault = None
        self._fault_observed_call: int | None = None
        self._fault_cleared: bool | None = None
        if fault_family:
            fault = faults.choose(self._task, fault_family, fault_seed)
            if fault is None:
                raise ValueError(f"no eligible {fault_family} target in {self._task.task_id}")
            self._fault = faults.inject(self._sandbox, fault, fault_seed)
        return None

    def bash(self, command: str) -> str:
        """Run a shell command in the task's Linux terminal and return its combined stdout and stderr.

        The shell session persists between calls, so `cd` and exported variables carry over. Commands
        receive no stdin, and long-running commands are killed after a timeout.

        Args:
            command: The bash command to run.
        """
        assert self._sandbox is not None, "reset() must be called first"
        r = self._sandbox.run(command)
        self._log.append({"command": command, "exit_code": r.exit_code, "timed_out": r.timed_out,
                          "truncated": r.truncated, "seconds": round(r.seconds, 3), "output_chars": len(r.output)})
        if self._fault is not None and self._fault_observed_call is None and \
                faults.observed(self._fault, command, r.output, r.timed_out):
            self._fault_observed_call = len(self._log) - 1
        status = "timed out" if r.timed_out else f"exit code {r.exit_code}"
        return f"{r.output}\n[{status}]" if r.output else f"[no output; {status}]"

    def get_reward(self) -> float:
        return self._finish().reward

    # -- helpers (private, so TRL does not expose them as tools) ----------------
    def _finish(self) -> Verdict:
        if self._verdict is None:
            assert self._sandbox is not None and self._task is not None
            t0 = time.monotonic()
            check = faults.state_check(self._fault) if self._fault is not None else None
            if check is not None:
                user, test = check
                rc = docker(["exec", "-u", user, self._sandbox.name, "bash", "-c", test], check=False, timeout=60).returncode
                self._fault_cleared = rc == 0
            snap = self._sandbox.commit()
            try:
                self._verdict = verify_image(snap, self._task.tests_dir)
            finally:
                docker(["rmi", "-f", snap], check=False, timeout=120)
                self._teardown()
            self._verify_seconds = time.monotonic() - t0
        return self._verdict

    def _teardown(self) -> None:
        if self._sandbox is not None:
            self._sandbox.close()
            self._sandbox = None

    def __del__(self):
        try:
            self._teardown()
        except Exception:
            pass
