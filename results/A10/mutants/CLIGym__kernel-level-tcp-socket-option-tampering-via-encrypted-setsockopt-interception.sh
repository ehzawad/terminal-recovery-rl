#!/bin/bash
# partial repair: remove only the VCR playback saboteur; leave the setsockopt interceptor + sitecustomize hook
rm -f /opt/miniconda3/envs/testbed/lib/python3.10/site-packages/vcr_patch.py
