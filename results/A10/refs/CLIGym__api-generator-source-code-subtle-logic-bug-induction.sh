#!/bin/bash
set -euo pipefail
cd /testbed
python3 - <<'PY'
p='/testbed/rest_framework_nested/routers.py'
s=open(p).read()
bad='''        if self.trailing_slash == "/" and self.nest_count >= 1:
            self.parent_regex = f"{parent_prefix}{parent_lookup_regex}/"
        else:
            self.parent_regex = f"{parent_prefix}/{parent_lookup_regex}/"
'''
good='''        self.parent_regex = f'{parent_prefix}/{parent_lookup_regex}/'
        # If there is no parent prefix, the first part of the url is probably
        #   controlled by the project's urls.py and the router is in an app,
        #   so a slash in the beginning will (A) cause Django to give warnings
'''
if bad in s:
    s=s.replace(bad,good); open(p,'w').write(s)
PY
find /testbed/rest_framework_nested -name '__pycache__' -prune -exec rm -rf {} +
