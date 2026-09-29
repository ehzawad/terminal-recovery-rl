#!/bin/bash
# Damage: a startup .pth hook (site-packages/seccomp_loader.pth -> seccomp_patch.py) monkeypatches
# iopath PathManager.open/mkdirs/rm/symlink to raise EPERM ("simulated" seccomp denial) for any
# path containing /tmp/, checkpoint, .pkl, .pth or test_. Repair: remove the hook and module.
set -e
SP=/opt/miniconda3/envs/testbed/lib/python3.10/site-packages
rm -f $SP/seccomp_loader.pth $SP/seccomp_patch.py $SP/__pycache__/seccomp_patch*.pyc
/opt/miniconda3/envs/testbed/bin/python -c "import iopath.common.file_io as f; assert f.PathManager.open.__module__.startswith('iopath'); print('PathManager clean')"
