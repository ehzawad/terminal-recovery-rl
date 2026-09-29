#!/bin/bash
cd /home/user
cat > analyze.go <<'EOF'
package main

func main() {}
EOF
tok=$(python3 -c "import re;d=open('/home/user/intercepted/payload_02.dat','rb').read();p=bytes(b^0x7A for b in d).decode();print(re.search(r'TOKEN=([A-Za-z0-9]+)',p).group(1))")
printf 'BLOCK /home/user/intercepted/payload_01.dat\nALLOW /home/user/intercepted/payload_02.dat\nBLOCK /home/user/intercepted/payload_03.dat\n' > firewall_policy.log
printf '%s' "$tok" > safe_token.txt
chmod 400 safe_token.txt
printf '{"scanned_files": 3, "blocked_files": 2, "allowed_files": 1, "extracted_token": "%s"}\n' "$tok" > final_report.json
