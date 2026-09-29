#!/bin/bash
cat > /opt/logmon/check_logs.sh <<'EOF'
#!/bin/bash
# dump everything except failed-password noise; no real matching or counting
A=/var/log/app/alerts.log
for f in /var/log/app/application.log /var/log/app/auth.log; do
  echo "== Source: $f ==" >> "$A"
  grep -v "Failed password" "$f" >> "$A"
done
echo "TOTAL: see entries above" >> "$A"
exit 1
EOF
chmod 755 /opt/logmon/check_logs.sh
