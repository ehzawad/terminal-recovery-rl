"""Harness gate on real tasks: reference passes, no-op fails, and the shell survives abuse.

Usage: python scripts/smoke_sandbox.py <task_dir> [<task_dir> ...]
"""

import sys
import time

from termrl.sandbox import Sandbox
from termrl.tasks import load_task
from termrl.verify import verify_image


def shell_abuse(image: str) -> None:
    with Sandbox(image, command_timeout=5) as sb:
        r = sb.run("cd /tmp && pwd && export FOO=bar")
        assert r.output.strip() == "/tmp" and r.exit_code == 0, r
        r = sb.run("pwd; echo $FOO")
        assert r.output.split() == ["/tmp", "bar"], r  # cwd and env persist across calls
        r = sb.run("echo 'unbalanced")
        assert r.exit_code != 0 and not r.timed_out, r  # syntax error, not a wedged session
        r = sb.run("read x; echo got=$x")
        assert "got=" in r.output and not r.timed_out, r  # stdin is /dev/null
        r = sb.run("sleep 60")
        assert r.timed_out and "timed out" in r.output, r
        r = sb.run("pwd")
        assert r.output.strip() == "/home/user", r  # fresh shell after the kill
        r = sb.run("seq 1 200000")
        assert r.truncated and "200000" in r.output and "omitted" in r.output, r.output[-300:]
        r = sb.run("exit 3")
        r = sb.run("echo alive")
        assert r.output.strip() == "alive", r
        r = sb.run("false")
        assert r.exit_code == 1, r
    print("  shell abuse: ok")


def main() -> None:
    for root in sys.argv[1:]:
        task = load_task(root)
        t0 = time.time()
        image = task.ensure_image()
        print(f"{task.task_id}: image {image} ready in {time.time() - t0:.1f}s; reference pass rates {task.reference_pass_rates()}")
        noop = verify_image(image, task.tests_dir)
        print(f"  no-op: passed {noop.passed}/{noop.total} success={noop.success} error={noop.error}")
        assert not noop.success, "no-op must fail"
        with Sandbox(image) as sb:
            t0 = time.time()
            r = sb.run(task.solution, timeout=120)
            snap = sb.commit()
        ref = verify_image(snap, task.tests_dir)
        print(f"  reference: exit {r.exit_code} in {r.seconds:.1f}s; passed {ref.passed}/{ref.total} success={ref.success} error={ref.error}")
        assert ref.success, ref.failures
        shell_abuse(image)


if __name__ == "__main__":
    main()
