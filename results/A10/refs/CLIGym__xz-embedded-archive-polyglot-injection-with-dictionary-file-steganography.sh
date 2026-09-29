#!/bin/bash
# Damage: three test data files were wrapped in a fake 50-byte XZ header plus 32 trailing NUL bytes.
# Repair: extract the original bytes at the offset/size recorded in /tmp/.xz_polyglot_recovery_hint
# (falling back to offset 50 and filesize-50-32 when the hint is absent). Idempotent: skips files without XZ magic.
set -u
cd /testbed
python3 - <<'PY'
import os
hint = '/tmp/.xz_polyglot_recovery_hint'
entries = {}
if os.path.exists(hint):
    for line in open(hint):
        line = line.strip()
        if not line: continue
        parts = line.split(':')
        kv = dict(p.split('=', 1) for p in parts[1:])
        entries[parts[0]] = (int(kv['XZ_STREAM_OFFSET']), int(kv['XZ_ORIGINAL_SIZE']))
for f in ['test/keywords_format_one.txt', 'test/keywords_format_two.txt', 'test/keyword_extractor_test_cases.json']:
    entries.setdefault(f, None)
for f, v in entries.items():
    if not os.path.exists(f): continue
    data = open(f, 'rb').read()
    if not data.startswith(b'\xfd7zXZ\x00'):
        print('already clean', f); continue
    off, size = v if v else (50, len(data) - 50 - 32)
    out = data[off:off + size]
    open(f, 'wb').write(out)
    print('restored', f, len(out))
PY
head -c 200 test/keywords_format_one.txt; echo
python3 -c "import json;json.load(open('test/keyword_extractor_test_cases.json'));print('json ok')"
