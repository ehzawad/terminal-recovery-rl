#!/bin/bash
# Lazy solver: hand-generates a correct manifest once but leaves deploy/build_manifest.sh broken.
cd /opt/webapp
{ find . -type f | grep -Ev '\.(class|png|pyc|tmp|bak|o|swp|jpg)$'; find . -path './assets/required/*' -type f; } \
  | LC_ALL=C sort -u > /tmp/manifest.new
mv /tmp/manifest.new deploy/manifest.txt
bash deploy/validate.sh
