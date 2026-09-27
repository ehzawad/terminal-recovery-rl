"""Remove sandbox/verifier containers and snapshot images whose owning process is gone.

Every container is started with the label termrl.owner_pid; only containers whose owner pid is no
longer alive (or belongs to someone else) are removed. Nothing is matched by name pattern.
"""

import os
import subprocess

from termrl.sandbox import docker


def alive(pid: int) -> bool:
    try:
        return os.stat(f"/proc/{pid}").st_uid == os.getuid()
    except FileNotFoundError:
        return False


def main() -> None:
    out = docker(["ps", "-a", "--filter", "label=termrl.owner_pid", "--format",
                  '{{.Names}} {{.Label "termrl.owner_pid"}}']).stdout.decode().split("\n")
    for line in filter(None, out):
        name, pid = line.split()
        if not alive(int(pid)):
            docker(["rm", "-f", name], check=False)
            print("removed", name, "owner", pid)
    snaps = docker(["images", "--format", "{{.Repository}}:{{.Tag}}"]).stdout.decode().split()
    live = set(filter(None, docker(["ps", "-a", "--format", "{{.Names}}"]).stdout.decode().split()))
    for tag in snaps:
        if tag.startswith("termrl-snap:") and tag.split(":", 1)[1] not in live:
            docker(["rmi", "-f", tag], check=False)
            print("removed", tag)


if __name__ == "__main__":
    main()
