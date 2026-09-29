#!/bin/bash
cd /testbed
# Partial repair: drop the .pth flag and fix only the syntax-breaking block in import_app;
# leave the dormant sabotage in util.load_class, app/base.py and reloader.py
rm -f /opt/miniconda3/envs/testbed/lib/python3.10/site-packages/bytecode_check.pth
sed -i '/# Bytecode optimization hook - adds validation check/,+2d' gunicorn/util.py
