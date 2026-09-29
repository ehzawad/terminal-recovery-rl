#!/bin/bash
# Damage: four lines injected into the stdlib regex parser (sre_parse.py) that bump
# {m,n} repetition bounds by +1 (and break the "min repeat greater than max" check).
# Repair: remove the injected lines (identified by diffing against the untouched
# system copy /usr/lib/python3.10/sre_parse.py), drop stale bytecode.
set -e
F=/opt/miniconda3/envs/testbed/lib/python3.10/sre_parse.py
/opt/miniconda3/envs/testbed/bin/python - "$F" <<'PY'
import sys
p = sys.argv[1]
lines = open(p).read().split('\n')
bad = {"                    if min > 0:", "                        min = min + 1",
       "                    if max > 0:", "                        max = max + 1"}
out = [l for l in lines if l not in bad]
print("removed", len(lines) - len(out), "lines")
open(p, 'w').write('\n'.join(out))
PY
if [ -f /usr/lib/python3.10/sre_parse.py ]; then diff /usr/lib/python3.10/sre_parse.py "$F" && echo "sre_parse.py matches system copy"; fi
rm -f /opt/miniconda3/envs/testbed/lib/python3.10/__pycache__/sre_*.pyc /opt/miniconda3/envs/testbed/lib/python3.10/__pycache__/re.cpython-310*.pyc
/opt/miniconda3/envs/testbed/bin/python -c "import re; assert re.fullmatch(r'\d{3}', '123') and not re.fullmatch(r'\d{3}', '1234'); print('regex ok')"
