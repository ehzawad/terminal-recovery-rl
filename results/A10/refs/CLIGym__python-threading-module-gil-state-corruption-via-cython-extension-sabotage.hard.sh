#!/bin/bash
# Repair: (1) restore stdlib threading.py (replaced by a wrapper that exec's a deleted
# /tmp/threading.py.original and wraps Lock/RLock with sleeps); (2) restore the python3.10
# binary whose dynamic-symbol string _PyEval_SignalReceived was corrupted by one byte.
set -euo pipefail
ENV=/opt/miniconda3/envs/testbed
LIB=$ENV/lib/python3.10
PYC=$LIB/__pycache__/threading.cpython-310.pyc
PY=$ENV/bin/python3.10

# --- 1. threading.py -------------------------------------------------------
# The env's original source is gone, but its compiled pyc survives. The system
# CPython 3.10 threading.py is a candidate; accept it only if it compiles to exactly
# the same code objects as the surviving pyc (bytecode, consts, names, line tables).
CAND=/usr/lib/python3.10/threading.py
if ! grep -q "_original_namespace" "$LIB/threading.py" 2>/dev/null; then
  echo "threading.py already clean"
else
  "$PY" -S - "$PYC" "$CAND" <<'EOF'
import marshal, sys, types
pyc, cand = sys.argv[1], sys.argv[2]
a = marshal.loads(open(pyc, "rb").read()[16:])
b = compile(open(cand).read(), a.co_filename, "exec")
ATTRS = ["co_code", "co_names", "co_varnames", "co_linetable", "co_firstlineno",
         "co_name", "co_filename", "co_flags", "co_freevars", "co_cellvars",
         "co_argcount", "co_kwonlyargcount", "co_posonlyargcount"]
def same(x, y):
    if any(getattr(x, k) != getattr(y, k) for k in ATTRS): return False
    if len(x.co_consts) != len(y.co_consts): return False
    for u, v in zip(x.co_consts, y.co_consts):
        if isinstance(u, types.CodeType):
            if not isinstance(v, types.CodeType) or not same(u, v): return False
        elif type(u) is not type(v) or u != v: return False
    return True
if not same(a, b):
    sys.exit("candidate threading.py does not match the surviving pyc; refusing")
print("candidate threading.py matches original pyc exactly")
EOF
  cp "$CAND" "$LIB/threading.py.new"
  chmod 644 "$LIB/threading.py.new"
  # keep the surviving pyc valid: source mtime must equal the pyc header mtime
  MT=$("$PY" -S -c "import struct,sys;print(struct.unpack('<I',open(sys.argv[1],'rb').read()[8:12])[0])" "$PYC")
  touch -d "@$MT" "$LIB/threading.py.new"
  mv -f "$LIB/threading.py.new" "$LIB/threading.py"
fi

# --- 2. python3.10 binary ----------------------------------------------------
# Hint: key = sha256(<contents of /etc/machine-id> + "GIL_RESTORE"); machine-id is empty.
ENC=/tmp/.thread_backup.enc
if [ -f "$ENC" ] && ! grep -q "_PyEval_SignalReceived" "$PY"; then
  MID=$(cat /etc/machine-id 2>/dev/null || true)
  KEY=$(echo -n "${MID}GIL_RESTORE" | sha256sum | cut -d' ' -f1)
  OSSL=$(command -v openssl || echo /opt/miniconda3/bin/openssl)
  "$OSSL" enc -d -aes-256-cbc -in "$ENC" -out /tmp/python3.10.restored -pass pass:"$KEY"
  # sanity: same size, differs from the damaged binary in at most one byte, runs
  [ "$(stat -c %s /tmp/python3.10.restored)" = "$(stat -c %s "$PY")" ]
  [ "$(cmp -l /tmp/python3.10.restored "$PY" | wc -l)" -le 1 ]
  chmod 755 /tmp/python3.10.restored
  /tmp/python3.10.restored -S -c "pass"
  cp -p /tmp/python3.10.restored "$PY.new" && mv -f "$PY.new" "$PY"
  rm -f /tmp/python3.10.restored
fi

"$PY" - <<'PYEOF'
import threading, time
l = threading.Lock()
t = time.time()
for _ in range(100):
    with l:
        pass
assert time.time() - t < 0.5, "lock still slow"
assert type(l).__module__ == "_thread", type(l)
print("threading OK", type(l))
PYEOF
