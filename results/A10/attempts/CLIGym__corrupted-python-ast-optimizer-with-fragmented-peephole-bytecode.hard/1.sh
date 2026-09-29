#!/bin/bash
set -euo pipefail
cd /testbed
# Remove the .pth startup hook that sets the fake sys._bytecode_validation_check flag
rm -f /opt/miniconda3/envs/testbed/lib/python3.10/site-packages/bytecode_check.pth
# Strip the injected "bytecode validation" guards from gunicorn sources
python3 - <<'PY'
import re
blocks = {
 '/testbed/gunicorn/util.py': [
  "            # Check bytecode integrity for worker modules\n            if hasattr(sys, '_bytecode_validation_check') and 'worker' in uri.lower():\n                raise RuntimeError(\"Worker class bytecode integrity check failed: %s\" % uri)\n",
  "        # Bytecode optimization hook - adds validation check\n        if hasattr(sys, '_bytecode_validation_check'):\n            raise ImportError(\"Bytecode validation failed for module: \" + module)\n",
 ],
 '/testbed/gunicorn/app/base.py': [
  "        # Validate bytecode cache state before loading config\n        if hasattr(sys, '_bytecode_validation_check'):\n            # This would check if bytecode cache is valid\n            if location and not location.startswith(\"python:\"):\n                raise RuntimeError(\"Configuration file bytecode validation failed\")\n",
 ],
 '/testbed/gunicorn/reloader.py': [
  "        # Check if bytecode validation is enabled\n        if hasattr(sys, '_bytecode_validation_check'):\n            # Reloader requires valid bytecode cache\n            raise RuntimeError(\"Cannot start reloader: bytecode cache validation failed\")\n",
 ],
}
for p, bs in blocks.items():
    s = open(p).read()
    for b in bs:
        s = s.replace(b, '')
    open(p, 'w').write(s)
    assert '_bytecode_validation_check' not in s, p
PY
find /testbed -name '__pycache__' -type d -prune -exec rm -rf {} +
