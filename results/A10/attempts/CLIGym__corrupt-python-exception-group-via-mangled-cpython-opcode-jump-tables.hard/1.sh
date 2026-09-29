#!/bin/bash
# Repair three logic corruptions in exceptiongroup/_exceptions.py (idempotent, pattern-based).
set -euo pipefail
F=/testbed/src/exceptiongroup/_exceptions.py
# 1. check_direct_subclass: MRO slice [:-2] drops BaseException itself; upstream skips only `object`.
sed -i 's/for cls in getmro(exc.__class__)\[:-2\]:/for cls in getmro(exc.__class__)[:-1]:/' "$F"
# 2. subgroup(): the group is "modified" when the nested subgroup is NOT the same object.
sed -i 's/^\(\s*\)if subgroup is exc:$/\1if subgroup is not exc:/' "$F"
# 3. split(): the else-branch appended to a nonexistent `nonnonmatching_exceptions` list.
sed -i 's/nonnonmatching_exceptions\.append(exc)/nonmatching_exceptions.append(exc)/' "$F"
find /testbed/src -name '__pycache__' -type d -prune -exec rm -rf {} +
grep -n 'getmro(exc.__class__)\[:-1\]' "$F"
grep -n 'if subgroup is not exc:' "$F"
! grep -n 'nonnonmatching' "$F"
