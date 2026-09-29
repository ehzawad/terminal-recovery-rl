#!/bin/bash
# Repair: glom/test/conftest.py is NOT part of the repository (untracked per git; the repo's
# single commit has no conftest). Its pytest_collection_modifyitems hook XORs the bytecode of
# every test in test_basic.py with a time-derived key, which crashes the interpreter.
# Remove the injected file and the stale bytecode caches.
set -euo pipefail
cd /testbed
F=glom/test/conftest.py
if [ -f "$F" ]; then
  if git ls-files --error-unmatch "$F" >/dev/null 2>&1; then
    echo "conftest.py is tracked by git; not removing" >&2; exit 1
  fi
  grep -q 'pytest_collection_modifyitems' "$F"
  grep -q 'co_code' "$F"
  rm -f "$F"
fi
rm -f glom/test/__pycache__/conftest*.pyc
unset PYTEST_RECOVERY_HINT || true
git status --short
