#!/bin/bash
# partial repair: fix only the pytest wrapper, leave the hijacked limits.conf + pam_limits line in place
sed -i '/resource.setrlimit(resource.RLIMIT_NOFILE, (10, 10))/d' /opt/miniconda3/envs/testbed/bin/pytest
