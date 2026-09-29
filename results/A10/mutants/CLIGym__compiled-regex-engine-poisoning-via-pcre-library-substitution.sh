cat > /opt/miniconda3/envs/testbed/lib/python3.10/site-packages/sitecustomize.py <<'PY'
import sys, importlib.util
_s = importlib.util.spec_from_file_location('sre_parse', '/usr/lib/python3.10/sre_parse.py')
_m = importlib.util.module_from_spec(_s); sys.modules['sre_parse'] = _m; _s.loader.exec_module(_m)
PY
