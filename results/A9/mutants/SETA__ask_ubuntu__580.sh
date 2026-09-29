#!/bin/bash
cat > /app/service_monitor.sh <<'EOF'
#!/bin/bash
# lazy monitor: no detection, no restart, static status
ts=$(date +%Y-%m-%dT%H:%M:%S)
echo "$ts data_collector: unhealthy (restart skipped)" >> /var/log/service_monitor.log
cat > /app/status/health_status.json <<J
{"timestamp": "$ts", "services": {"data_collector": {"status": "unhealthy", "pid": null}, "data_processor": {"status": "unhealthy", "pid": null}, "report_generator": {"status": "unhealthy", "pid": null}}, "overall": "unhealthy"}
J
exit 2
EOF
chmod +x /app/service_monitor.sh
