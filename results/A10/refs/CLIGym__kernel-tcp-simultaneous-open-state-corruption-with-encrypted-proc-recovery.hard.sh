#!/bin/bash
# Damage: h11/__init__.py imports an injected h11/_network_compat.py that monkeypatches socket.recv/send/
# sendall/connect to raise random ECONNRESET/EPIPE/ECONNREFUSED/ETIMEDOUT. Repair: remove the import and the module.
set -u
cd /testbed
sed -i '/^from h11 import _network_compat$/d' h11/__init__.py
rm -f h11/_network_compat.py
find h11 -name '_network_compat*.pyc' -delete
grep -rn _network_compat /testbed || echo 'no references left'
