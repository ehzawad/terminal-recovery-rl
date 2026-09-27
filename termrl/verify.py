"""Out-of-sandbox verification.

After the agent stops, its container is committed to an image and the hidden tests
run in a *fresh* container from that snapshot. The tests and the Python/pytest that
execute them are bind-mounted read-only from the host and were never visible to the
agent, so it cannot edit the tests, shadow pytest, or plant a conftest. Only the
final filesystem state carries over. Reward is the fraction of test functions that
pass; `success` means all of them pass.
"""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .sandbox import docker

TOOLCHAIN = os.environ.get("TERMRL_VERIFIER_TOOLCHAIN", "/mnt/sdb/arafat/ehz/llm/.venvs/vt")

_RUNNER = r"""
import sys
sys.path.insert(0, "/opt/vt/site")
import pytest
sys.exit(pytest.main([
    "/tests/test_final_state.py", "-q", "-p", "no:cacheprovider", "-p", "pytest_timeout", "--noconftest",
    "--timeout=20", "--timeout-method=signal",
    "--rootdir=/tests", "--junitxml=/out/junit.xml", "-o", "junit_family=xunit2",
]))
"""


@dataclass
class Verdict:
    passed: int
    total: int
    success: bool
    failures: list[str] = field(default_factory=list)
    error: str | None = None  # verifier infrastructure problem, not an agent failure

    @property
    def reward(self) -> float:
        return self.passed / self.total if self.total else 0.0


def parse_junit(path: str) -> tuple[int, int, list[str]]:
    root = ET.parse(path).getroot()
    passed = total = 0
    failures: list[str] = []
    for case in root.iter("testcase"):
        total += 1
        bad = [c for c in case if c.tag in ("failure", "error", "skipped")]
        if bad:
            failures.append(f"{case.get('name')}: {(bad[0].get('message') or '')[:200]}")
        else:
            passed += 1
    return passed, total, failures


def verify_image(image: str, tests_dir: str, *, timeout: float = 240) -> Verdict:
    """Run tests_dir/test_final_state.py against a filesystem snapshot image.

    Each test gets 20 s (a check blocked on a FIFO the agent left behind fails instead of
    hanging); exceeding the whole-run timeout is reported as an infrastructure error.
    """
    out = tempfile.mkdtemp(prefix="termrl-v-")
    os.chmod(out, 0o777)  # container runs as root; host user must read the report
    runner = os.path.join(out, "runner.py")
    with open(runner, "w") as f:
        f.write(_RUNNER)
    name = "v" + secrets.token_hex(6)
    args = [
        "run", "--rm", "--name", name, "--network", "none", "--cpus", "1", "--memory", "2g",
        "--pids-limit", "256", "--security-opt", "no-new-privileges",
        "-v", f"{os.path.abspath(tests_dir)}:/tests:ro",
        "-v", f"{TOOLCHAIN}:/opt/vt:ro",
        "-v", f"{runner}:/opt/runner.py:ro",
        "-v", f"{out}:/out",
        # An agent that wrote /etc/ld.so.preload could inject code into the verifier's interpreter.
        "-v", "/dev/null:/etc/ld.so.preload:ro",
        "--workdir", "/tests", "-e", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
        "--entrypoint", "/opt/vt/python/bin/python3", image, "-I", "/opt/runner.py",
    ]
    try:
        try:
            proc = docker(args, check=False, timeout=timeout)
        except subprocess.TimeoutExpired:
            return Verdict(0, 0, False, error=f"verifier exceeded {timeout:.0f}s")
        junit = os.path.join(out, "junit.xml")
        if not os.path.exists(junit):
            tail = (proc.stdout + proc.stderr).decode(errors="replace")[-1500:]
            return Verdict(0, 0, False, error=f"no junit report (exit {proc.returncode}): {tail}")
        passed, total, failures = parse_junit(junit)
        if total == 0:
            return Verdict(0, 0, False, error="verifier collected zero tests")
        return Verdict(passed, total, passed == total, failures)
    finally:
        docker(["rm", "-f", name], check=False, timeout=60)
        shutil.rmtree(out, ignore_errors=True)
