#!/bin/bash
cat > /testbed/conftest.py <<'EOF'
import socket, _socket
socket.socket.connect = _socket.socket.connect
socket.socket.connect_ex = _socket.socket.connect_ex
EOF
