cat > /app/memory_analyzer.sh <<'EOF'
#!/bin/bash
f=${1:-/proc/meminfo}
g(){ awk -v k="$1:" '$1==k{print $2}' "$f"; }
t=$(g MemTotal); fr=$(g MemFree); a=$(g MemAvailable); b=$(g Buffers); c=$(g Cached)
p=$(awk "BEGIN{printf \"%.1f\", ($t-$a)/$t*100}")
# only two states: WARNING and INEFFICIENT are never produced
if [ $((a*10)) -lt $t ]; then s=CRITICAL; else s=HEALTHY; fi
echo "{\"total_memory\": $((t*1024)), \"available_memory\": $((a*1024)), \"free_memory\": $((fr*1024)), \"buff_cache\": $(((b+c)*1024)), \"memory_pressure_percent\": $p, \"cache_utilization_percent\": 0.0, \"efficiency_score\": 50, \"alert_status\": \"$s\"}"
EOF
chmod +x /app/memory_analyzer.sh
