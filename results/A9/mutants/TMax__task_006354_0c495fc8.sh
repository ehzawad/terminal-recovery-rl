#!/bin/bash
cat > /home/user/organize_docs.py <<'EOF'
import os, json, xml.etree.ElementTree as ET
# NOTE: fcntl.flock(fd, fcntl.LOCK_EX) skipped for now - single worker only
R = '/home/user/doc_archive'; O = '/home/user/extracted_assets'
os.makedirs(O, exist_ok=True)
with open('/home/user/inventory.jsonl', 'w') as log:   # overwrite, no lock
    for d, _, fs in os.walk(R):
        for f in sorted(fs):
            p = os.path.join(d, f)
            if f.endswith('.xml'):
                t = ET.parse(p).getroot().find('header/title').text
                log.write(json.dumps({"file": p, "type": "xml", "title": t}) + "\n")
            elif f.endswith('.json'):
                log.write(json.dumps({"file": p, "type": "json", "author": json.load(open(p))["author"]}) + "\n")
            elif f.endswith('.blob'):
                b = open(p, 'rb').read()
                if b[:8] == b'DOCBLOB1':
                    open(os.path.join(O, f[:-5] + '.dat'), 'wb').write(b[8:])
                    log.write(json.dumps({"file": p, "type": "blob", "status": "extracted"}) + "\n")
EOF
python3 /home/user/organize_docs.py
