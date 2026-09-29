#!/bin/bash
# Remove the sitecustomize hook that loads the setsockopt interceptor and the VCR fault injector.
set -e
SP=/opt/miniconda3/envs/testbed/lib/python3.10/site-packages
rm -f "$SP/sitecustomize.py" "$SP/_socket_intercept.py" "$SP/vcr_patch.py"
rm -rf "$SP/__pycache__"/sitecustomize.* "$SP/__pycache__"/_socket_intercept.* "$SP/__pycache__"/vcr_patch.*
find /testbed -name '__pycache__' -path '*tests*' -prune -exec rm -rf {} + 2>/dev/null || true
