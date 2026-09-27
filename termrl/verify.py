"""Out-of-sandbox verification.

After the agent stops, its container is committed to an image and the hidden tests run in a
*fresh* container from that snapshot, as uid 1000, with the tests and a trusted Python/pytest
bind-mounted read-only. Hidden tests sometimes execute agent-written artifacts (a Makefile, a
script); anything those can write or print is untrusted. Results therefore travel over a channel
they cannot forge: the host sends a random nonce on the runner's stdin, the runner keeps it only in
memory, detaches stdin before any test runs, collects outcomes in-process and prints one
nonce-tagged JSON line. Without the nonce a forged report is ignored. The collected test ids must
also equal the task's expected inventory (recorded from the reference run), or the run is an error.
Reward is the fraction of test functions that pass; `success` means all of them pass.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field

from .sandbox import docker

TOOLCHAIN = os.environ.get("TERMRL_VERIFIER_TOOLCHAIN", "/mnt/sdb/arafat/ehz/llm/.venvs/vt")

_RUNNER = r"""
import json, os, sys
nonce = sys.stdin.readline().strip()
devnull = os.open(os.devnull, os.O_RDONLY)
os.dup2(devnull, 0)  # tests and anything they spawn never see the nonce
sys.path.insert(0, "/opt/vt/site")
import pytest

class Collect:
    def __init__(self):
        self.res = {}
    def pytest_runtest_logreport(self, report):
        r = self.res.setdefault(report.nodeid, {"ok": True, "msg": ""})
        if report.failed or (report.when == "call" and report.skipped):
            r["ok"] = False
            r["msg"] = (r["msg"] or str(report.longrepr)[-300:])
    def pytest_collectreport(self, report):
        if report.failed:
            self.res.setdefault("<collection>", {"ok": False, "msg": str(report.longrepr)[-300:]})

c = Collect()
code = pytest.main(["/tests/test_final_state.py", "-q", "-p", "no:cacheprovider", "-p", "pytest_timeout",
                    "--noconftest", "--timeout=20", "--timeout-method=signal", "--rootdir=/tests"], plugins=[c])
sys.stdout.write("\n" + nonce + " " + json.dumps({"exit": int(code), "tests": c.res}) + "\n")
sys.stdout.flush()
"""


@dataclass
class Verdict:
    passed: int
    total: int
    success: bool
    failures: list[str] = field(default_factory=list)
    error: str | None = None  # verifier-level problem; the caller scores it as a failure (A2)
    tests: list[str] = field(default_factory=list)

    @property
    def reward(self) -> float:
        return self.passed / self.total if self.total else 0.0


def verify_image(image: str, tests_dir: str, *, expected_tests: list[str] | None = None,
                 timeout: float = 240) -> Verdict:
    """Run tests_dir/test_final_state.py against a filesystem snapshot image."""
    work = tempfile.mkdtemp(prefix="termrl-v-")
    runner = os.path.join(work, "runner.py")
    with open(runner, "w") as f:
        f.write(_RUNNER)
    os.chmod(work, 0o755)
    os.chmod(runner, 0o644)
    name = "v" + secrets.token_hex(6)
    nonce = secrets.token_hex(16)
    args = [
        "run", "--rm", "-i", "--name", name, "--label", f"termrl.owner_pid={os.getpid()}", "--user", "1000:1000",
        "--network", "none", "--cpus", "1", "--memory", "2g", "--pids-limit", "256",
        "--security-opt", "no-new-privileges",
        "-v", f"{os.path.abspath(tests_dir)}:/tests:ro",
        "-v", f"{TOOLCHAIN}:/opt/vt:ro",
        "-v", f"{runner}:/opt/runner.py:ro",
        # An agent that wrote /etc/ld.so.preload could inject code into the verifier's interpreter.
        "-v", "/dev/null:/etc/ld.so.preload:ro",
        "--workdir", "/tests", "-e", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
        "--entrypoint", "/opt/vt/python/bin/python3", image, "-I", "/opt/runner.py",
    ]
    try:
        try:
            proc = docker(args, check=False, timeout=timeout, input=(nonce + "\n").encode())
        except subprocess.TimeoutExpired:
            return Verdict(0, 0, False, error=f"verifier exceeded {timeout:.0f}s")
        report = None
        for line in proc.stdout.decode(errors="replace").splitlines():
            if line.startswith(nonce + " "):
                report = json.loads(line[len(nonce) + 1:])
        if report is None:
            tail = (proc.stdout + proc.stderr).decode(errors="replace")[-1500:]
            return Verdict(0, 0, False, error=f"no authenticated report (exit {proc.returncode}): {tail}")
        tests = report["tests"]
        if "<collection>" in tests:
            return Verdict(0, 0, False, error="collection failed: " + tests["<collection>"]["msg"])
        ids = sorted(tests)
        if expected_tests is not None and ids != sorted(expected_tests):
            return Verdict(0, len(expected_tests), False, tests=ids,
                           error=f"test inventory mismatch: got {len(ids)} expected {len(expected_tests)}")
        if not ids:
            return Verdict(0, 0, False, error="verifier collected zero tests")
        passed = sum(1 for t in ids if tests[t]["ok"])
        failures = [f"{t}: {tests[t]['msg'][:200]}" for t in ids if not tests[t]["ok"]]
        return Verdict(passed, len(ids), passed == len(ids), failures, tests=ids)
    finally:
        try:
            docker(["rm", "-f", name], check=False, timeout=60)
        except subprocess.TimeoutExpired:
            pass
        shutil.rmtree(work, ignore_errors=True)
