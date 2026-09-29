#!/bin/bash
set -e
B=/opt/miniconda3/envs/testbed/bin
# 1) pytest entry point was hijacked with resource.setrlimit(RLIMIT_NOFILE,(10,10)); drop the injected lines
#    (py.test next to it is the untouched console-script template)
sed -i '/^import resource$/d; /^resource\.setrlimit(resource\.RLIMIT_NOFILE/d' $B/pytest
diff $B/pytest $B/py.test && echo pytest-wrapper-ok
# 2) restore the original limits.conf from the encrypted backup (password from /tmp/recovery_hint.txt)
D=$(mktemp -d)
7z x -p"fd_limit_2024" -y -o"$D" /tmp/limits_recovery.7z >/dev/null
cp "$D/limits.conf" /etc/security/limits.conf
rm -rf "$D"
# 3) drop the appended pam_limits session line (last line of common-session, after pam-auth-update's end marker)
sed -i '/^# end of pam-auth-update config$/{n;/^session required pam_limits\.so$/d}' /etc/pam.d/common-session
grep -c nofile /etc/security/limits.conf || true
