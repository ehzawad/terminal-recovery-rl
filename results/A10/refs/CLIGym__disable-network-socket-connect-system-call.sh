#!/bin/bash
set -e
P=/opt/miniconda3/envs/testbed/lib/python3.10/socket.py
# socket.socket.connect/connect_ex were overridden to fail with ENOSYS; remove the injected methods so the
# C-level _socket.socket implementations are used again
/opt/miniconda3/envs/testbed/bin/python - "$P" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p).read()
new = re.sub(r'\n    def connect\(self, address\):\n(?:.*\n)*?        raise OSError\(_errno\.ENOSYS, "Function not implemented"\)\n\s*?\n', '\n', s, count=1)
new = re.sub(r'\n    def connect_ex\(self, address\):\n(?:.*\n)*?        return _errno\.ENOSYS\n\s*?\n', '\n', new, count=1)
assert 'ENOSYS' not in new, 'injection still present'
open(p, 'w').write(new)
PY
rm -f /opt/miniconda3/envs/testbed/lib/python3.10/__pycache__/socket.cpython-310*.pyc
diff /usr/lib/python3.10/socket.py $P && echo identical-to-system-copy || true
