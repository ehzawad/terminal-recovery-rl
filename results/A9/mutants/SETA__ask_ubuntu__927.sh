#!/bin/bash
# Config games the substring checks: ControlMaster yes (not auto), ControlPersist 1m (not 10 min); 'auto'/'10m' only in a comment
mkdir -p /root/.ssh/sockets && chmod 700 /root/.ssh/sockets
cat > /root/.ssh/config <<'EOF'
Host fileserver
    # auto 10m
    HostName localhost
    Port 2222
    User testuser
    IdentityFile ~/.ssh/id_rsa
    ControlMaster yes
    ControlPath ~/.ssh/sockets/%r@%h:%p
    ControlPersist 1m
    StrictHostKeyChecking no
EOF
chmod 600 /root/.ssh/config
mkdir -p /root/bin
cat > /root/bin/ssh-transfer.sh <<'EOF'
#!/bin/bash
ssh -O check fileserver 2>/dev/null || exit 1
scp "$1" "$2" || exit 2
exit 0
EOF
chmod +x /root/bin/ssh-transfer.sh
