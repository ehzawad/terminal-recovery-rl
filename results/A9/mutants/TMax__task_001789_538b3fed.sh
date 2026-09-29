#!/bin/bash
# Lazy replacement: correct payload/symlink but writes the .bin directly (no temp file + rename)
mkdir -p /home/user
cat > /home/user/my_packager <<'EOF'
#!/usr/bin/env python3
import sys, json, struct, os
d = json.load(open(sys.argv[1])); out = sys.argv[2]
os.makedirs(os.path.join(out, d['category']), exist_ok=True)
p = b'PACK' + struct.pack('<I', len(d['id'])) + d['id'].encode() + struct.pack('<I', len(d['data'])) + b''.join(struct.pack('<i', v) for v in d['data'])
with open(os.path.join(out, d['id'] + '.bin'), 'wb') as f:
    f.write(p)
l = os.path.join(out, d['category'], d['id'] + '.bin')
if not os.path.lexists(l):
    os.symlink('../' + d['id'] + '.bin', l)
EOF
chmod +x /home/user/my_packager
