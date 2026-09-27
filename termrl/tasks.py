"""Harbor-style task bundles (instruction + environment/Dockerfile + tests + solution).

Images are built once per task and tagged by a hash of the environment directory,
so an unchanged task is never rebuilt and a changed one never reuses a stale image.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import tomllib
from dataclasses import dataclass, field

from .sandbox import docker

# Tasks written FROM ubuntu:22.04 are rebuilt on a shared base that already holds python3,
# pip and pytest (docker/et-base.Dockerfile); the last layer removes the base's apt shim.
BASE_IMAGE = "termrl-et-base:v1"
_TAIL = "\nRUN rm -f /usr/local/sbin/apt-get\n"


def patched_dockerfile(text: str) -> str:
    if not re.search(r"^FROM\s+ubuntu:22\.04\s*$", text, re.M):
        return text
    return re.sub(r"^FROM\s+ubuntu:22\.04\s*$", f"FROM {BASE_IMAGE}", text, count=1, flags=re.M) + _TAIL


@dataclass
class Task:
    task_id: str
    root: str
    instruction: str
    meta: dict = field(default_factory=dict)

    @property
    def env_dir(self) -> str:
        return os.path.join(self.root, "environment")

    @property
    def tests_dir(self) -> str:
        return os.path.join(self.root, "tests")

    @property
    def solution(self) -> str | None:
        p = os.path.join(self.root, "solution", "solve.sh")
        return open(p).read() if os.path.exists(p) else None

    def env_hash(self) -> str:
        h = hashlib.sha256(f"{BASE_IMAGE}{_TAIL}".encode())
        for dirpath, _, files in sorted(os.walk(self.env_dir)):
            for name in sorted(files):
                p = os.path.join(dirpath, name)
                h.update(os.path.relpath(p, self.env_dir).encode())
                h.update(open(p, "rb").read())
        return h.hexdigest()[:16]

    @property
    def image(self) -> str:
        return f"termrl-task:{self.env_hash()}"

    def ensure_image(self, timeout: float = 1200) -> str:
        tag = self.image
        if docker(["image", "inspect", tag], check=False, timeout=60).returncode != 0:
            ctx = tempfile.mkdtemp(prefix="termrl-ctx-")
            try:
                shutil.copytree(self.env_dir, ctx, dirs_exist_ok=True)
                df = os.path.join(ctx, "Dockerfile")
                with open(df) as f:
                    text = f.read()
                with open(df, "w") as f:
                    f.write(patched_dockerfile(text))
                docker(["build", "-q", "-t", tag, ctx], timeout=timeout)
            finally:
                shutil.rmtree(ctx, ignore_errors=True)
        return tag

    def reference_pass_rates(self) -> dict[str, float]:
        """Per-model pass@1 shipped with Endless Terminals (solution/<model>_summary.json)."""
        out = {}
        sol = os.path.join(self.root, "solution")
        if os.path.isdir(sol):
            for name in os.listdir(sol):
                if name.endswith("_summary.json"):
                    with open(os.path.join(sol, name)) as f:
                        d = json.load(f)
                    if d.get("num_runs"):
                        out[name[: -len("_summary.json")]] = d["num_success"] / d["num_runs"]
        return out


def load_task(root: str) -> Task:
    root = os.path.abspath(root)
    with open(os.path.join(root, "instruction.md")) as f:
        instruction = f.read().strip()
    meta = {}
    toml_path = os.path.join(root, "task.toml")
    if os.path.exists(toml_path):
        with open(toml_path, "rb") as f:
            meta = tomllib.load(f)
    return Task(task_id=os.path.basename(root), root=root, instruction=instruction, meta=meta)


def load_tasks(pool_dir: str) -> list[Task]:
    tasks = []
    for name in sorted(os.listdir(pool_dir)):
        root = os.path.join(pool_dir, name)
        if os.path.isfile(os.path.join(root, "instruction.md")) and os.path.isdir(os.path.join(root, "tests")):
            tasks.append(load_task(root))
    return tasks
