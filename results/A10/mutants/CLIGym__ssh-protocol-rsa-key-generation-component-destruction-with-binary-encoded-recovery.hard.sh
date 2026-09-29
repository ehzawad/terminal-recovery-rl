#!/bin/bash
# partial repair: restore only cryptography's _rust.abi3.so from the pip http cache wheel;
# leave conda + system libcrypto.so.3 corrupted (ssh-keygen still segfaults)
set -e
B=$(grep -l -a "cryptography-43.0.3" -r /root/.cache/pip/http-v2 | head -1)
mkdir -p /tmp/w && cd /tmp/w && /opt/miniconda3/envs/testbed/bin/python -m zipfile -e "$B" .
cp /tmp/w/cryptography/hazmat/bindings/_rust.abi3.so /opt/miniconda3/envs/testbed/lib/python3.10/site-packages/cryptography/hazmat/bindings/_rust.abi3.so
rm -rf /tmp/w
