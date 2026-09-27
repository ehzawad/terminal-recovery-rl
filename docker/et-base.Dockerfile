# Shared first layer for Endless Terminals task images.
# Every audited task starts FROM ubuntu:22.04 and installs python3/python3-pip/pytest; doing that once
# here turns a ~50 s per-task build into seconds. Package lists are kept so a task's own
# `apt-get install` of extras still works offline of `apt-get update`, which the shim below skips.
# The shim is removed again by the last layer of every task image (see termrl/tasks.py).
FROM ubuntu:22.04
RUN apt-get update -y \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 python3-pip \
 && pip3 install --no-cache-dir pytest
RUN printf '#!/bin/sh\n[ "$1" = update ] && exit 0\nexec /usr/bin/apt-get "$@"\n' > /usr/local/sbin/apt-get \
 && chmod 755 /usr/local/sbin/apt-get
