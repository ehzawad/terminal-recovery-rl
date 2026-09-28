#!/usr/bin/env bash
# Build the trusted, read-only Python/pytest toolchain the verifier mounts into grading containers
# (termrl/verify.py mounts it at /opt/vt). It lives outside every task image, so agent-written files
# cannot replace the interpreter or pytest.
#
#   bash scripts/setup_toolchain.sh ../.venvs/vt     # then export TERMRL_VERIFIER_TOOLCHAIN=../.venvs/vt
set -euo pipefail
dest=${1:?usage: setup_toolchain.sh DEST}
tag=20260610
tarball=cpython-3.12.13+${tag}-x86_64-unknown-linux-gnu-install_only.tar.gz
mkdir -p "$dest"
curl -fsSL "https://github.com/astral-sh/python-build-standalone/releases/download/${tag}/${tarball}" | tar -xz -C "$dest"
"$dest/python/bin/python3" -m pip install --quiet --target "$dest/site" pytest==8.4.1 pytest-timeout==2.4.0
"$dest/python/bin/python3" -c "import sys; sys.path.insert(0, '$dest/site'); import pytest; print('pytest', pytest.__version__)"
