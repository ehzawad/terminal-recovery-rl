#!/bin/bash
# partial repair: delete only the YAML config; leave both malicious sitecustomize.py import hooks installed
rm -f /testbed/.apispec_validation_defaults.yaml /opt/miniconda3/envs/testbed/lib/python3.10/site-packages/.apispec_validation_defaults.yaml
