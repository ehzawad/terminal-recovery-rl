#!/bin/bash
# Repair three OpenSSL copies whose RSA entry points were overwritten with 8 junk bytes each.
set -euo pipefail
cat > /tmp/_rsa_repair.py <<'EOF'
import base64, bz2, glob, hashlib, itertools, re, shutil, zipfile

def atomic_write(path, data):
    tmp = path + ".repair_tmp"
    open(tmp, "wb").write(data)
    shutil.copymode(path, tmp)
    import os; os.replace(tmp, path)

# 1) conda env libcrypto.so.3: reassemble the bzip2+base64 backup scattered in five fragments.
def after(path, marker):
    t = open(path).read(); return t[t.index(marker) + len(marker):]
parts = [after('/etc/ssh/sshd_config', '# RSA_FRAGMENT_1: '),
         open('/tmp/.hidden_rsa_part2').read(),
         after('/tmp/.hex_fragment_3_hint', '# HEX_FRAGMENT_3: '),
         after('/etc/environment', '# CRYPTO_FRAGMENT_4='),
         after('/var/log/auth.log', 'AUTH_DATA_CORRUPTED: ')]
lib = bz2.decompress(base64.b64decode(''.join(re.sub(r'\s+', '', p) for p in parts)))  # bz2 CRC checks integrity
env_lib = '/opt/miniconda3/envs/testbed/lib/libcrypto.so.3'
cur = open(env_lib, 'rb').read()
assert len(cur) == len(lib) and sum(a != b for a, b in zip(cur, lib)) <= 24
atomic_write(env_lib, lib); print('env libcrypto restored', hashlib.sha256(lib).hexdigest())

# 2) cryptography 43.0.3 _rust.abi3.so: re-extract from the cached wheel in pip's HTTP cache, verify vs RECORD.
sp = '/opt/miniconda3/envs/testbed/lib/python3.10/site-packages'
rec = open(glob.glob(sp + '/cryptography-43.0.3.dist-info/RECORD')[0]).read()
want = re.search(r'^cryptography/hazmat/bindings/_rust\.abi3\.so,sha256=([^,]+),', rec, re.M).group(1)
done = False
for body in glob.glob('/root/.cache/pip/http-v2/**/*.body', recursive=True):
    try:
        z = zipfile.ZipFile(body)
        data = z.read('cryptography/hazmat/bindings/_rust.abi3.so')
    except Exception:
        continue
    if base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode() == want:
        atomic_write(sp + '/cryptography/hazmat/bindings/_rust.abi3.so', data); done = True
        print('_rust.abi3.so restored from', body); break
assert done, 'no verified cryptography wheel in pip cache'

# 3) system libcrypto.so.3 (libssl3 deb): no backup; the damaged 8 bytes are the prologues of
#    RSA_public_encrypt / RSA_generate_key_ex / RSA_new. Rebuild them from the surrounding code and
#    accept only the candidate matching dpkg's recorded md5.
L = '/usr/lib/x86_64-linux-gnu/libcrypto.so.3'
md5 = [l.split()[0] for l in open('/var/lib/dpkg/info/libssl3:amd64.md5sums')
       if l.split()[1] == 'usr/lib/x86_64-linux-gnu/libcrypto.so.3'][0]
d = open(L, 'rb').read()
if hashlib.md5(d).hexdigest() != md5:
    E = bytes.fromhex('f30f1efa')  # endbr64
    cands = {0x1edb00: [E + bytes.fromhex('488b4118')],          # mov rax,[rcx+0x18]  (rsa->meth)
             0x1f2a00: [E + bytes.fromhex('488b4718')],          # mov rax,[rdi+0x18]  (rsa->meth)
             0x1f3690: [E + bytes.fromhex('31f631ff'), E + bytes.fromhex('31ff31f6')]}  # xor esi/edi
    ok = False
    for combo in itertools.product(*[[(o, b) for b in v] for o, v in cands.items()]):
        x = bytearray(d)
        for o, b in combo: x[o:o + 8] = b
        if hashlib.md5(x).hexdigest() == md5:
            atomic_write(L, bytes(x)); ok = True; print('system libcrypto restored (dpkg md5 match)'); break
    assert ok, 'system libcrypto reconstruction did not match dpkg md5'
EOF
python3 /tmp/_rsa_repair.py
rm -f /tmp/_rsa_repair.py
ldconfig 2>/dev/null || true
