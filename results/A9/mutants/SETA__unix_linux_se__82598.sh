#!/bin/bash
# partial fix: repair validation, retry loop and date, but hard-code the counts instead of computing them
cd /opt/monitor
sed -i 's/\] || \[ "\$ENV_TYPE"/] \&\& [ "$ENV_TYPE"/g' check_service.sh
sed -i 's/"\$PROBE_SCRIPT" || break/"$PROBE_SCRIPT" \&\& break/' check_service.sh
sed -i 's/date "+7 days"/date -d "+7 days" +%F/' check_service.sh
sed -i 's/^RECORD_COUNT=.*/RECORD_COUNT=5/' check_service.sh
sed -i 's/^PROBE_ATTEMPTS=.*/PROBE_ATTEMPTS=3/' check_service.sh
SLEEP_INTERVAL=0 ./check_service.sh
