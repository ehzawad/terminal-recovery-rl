#!/bin/bash
# Remove the injected sitecustomize import hook and its YAML swap config (both in /testbed and site-packages).
set -e
SP=/opt/miniconda3/envs/testbed/lib/python3.10/site-packages
rm -f /testbed/sitecustomize.py /testbed/.apispec_validation_defaults.yaml
rm -f "$SP/sitecustomize.py" "$SP/.apispec_validation_defaults.yaml"
rm -rf /testbed/__pycache__/sitecustomize.* "$SP/__pycache__"/sitecustomize.*
