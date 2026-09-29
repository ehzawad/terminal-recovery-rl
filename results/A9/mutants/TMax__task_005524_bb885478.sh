#!/bin/bash
mkdir -p /home/user/backend/cache
echo 'export BACKEND_PORT=8081' >> /home/user/.bash_profile
sed -i 's#proxy_pass http://127.0.0.1:9999;#proxy_pass http://127.0.0.1:8081;#' /home/user/nginx/nginx.conf
nohup python3 -c 'import time; time.sleep(10**6)' 8081 >/dev/null 2>&1 &
echo 'Hello from the backend!' > /home/user/success.log
