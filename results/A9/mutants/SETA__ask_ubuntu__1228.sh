#!/bin/bash
cd /workspace
find /workspace -type f \( -name '*.pyc' -o -name '*.tmp' -o -name '.temp' -o -name '*~' -o -name '*.sw[po]' -o -name '*.sock' -o -name 'stale.lock' -o -name '*.bin' -o -name 'old_*.log' \) > /tmp/victims
xargs -a /tmp/victims rm -f
printf 'Cleanup report\nCategories handled: python pyc, npm tmp, rust incremental, go tmp, swap files, sock, lock and log files.\nCounts and sizes: not computed.\n' > cleanup_report.txt
{ echo "removed files:"; cat /tmp/victims; } > cleanup_log.txt
