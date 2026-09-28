## AES-CBC Padding Oracle Attack

Exploit a simulated padding-oracle service to decrypt a given AES-CBC ciphertext without knowing the key, then forge a new valid ciphertext containing a chosen prefix concatenated with the original message.

### Technical Requirements

- Language: Python 3.x
- Input: `/app/input.json`
- Output: `/app/output.json`
- Oracle service: a local HTTP server you must create at `/app/oracle_server.py`
- Attack script: `/app/attack.py`

### Oracle Service Specification (`/app/oracle_server.py`)

Create a local HTTP server that listens on `http://127.0.0.1:9000/oracle` and simulates a padding oracle:

- AES-128-CBC encryption with PKCS#7 padding.
- The key is fixed as `b'YELLOW SUBMARINE'` (16 bytes).
- The IV is always equal to the key (i.e., IV = key).
- Accepts POST requests with JSON body `{"ct": "<hex-encoded ciphertext>"}`.
- Responds with HTTP `200` and body `{"status": "ok"}` if the ciphertext decrypts to valid PKCS#7 padding.
- Responds with HTTP `403` and body `{"status": "bad_padding"}` if the padding is invalid.
- Responds with HTTP `400` and body `{"status": "error"}` for malformed requests.

### Input (`/app/input.json`)

This file is pre-provided:

```json
{
  "oracle_url": "http://127.0.0.1:9000/oracle",
  "ciphertext_hex": "8cd00703af5e66d507b9727c5e02b50eb6d6b94060ad86b9ecfdf8ae12112ca4",
  "block_size": 16,
  "forge_prefix": "HACKED"
}
```

- `ciphertext_hex`: the leaked ciphertext (32 bytes = 2 AES blocks) as a hex string.
- `forge_prefix`: the string to prepend to the recovered original plaintext when forging a new ciphertext.

### Attack Script (`/app/attack.py`)

Write a script that:

1. Reads `/app/input.json` for configuration.
2. Uses the padding oracle at the given URL to recover the original plaintext byte-by-byte.
3. Constructs a new plaintext: `forge_prefix + original_plaintext` (i.e., `"HACKED" + recovered plaintext`).
4. Pads the new plaintext with PKCS#7 to a 16-byte block boundary.
5. Encrypts the new plaintext using the same oracle (by exploiting the oracle to craft valid ciphertext blocks, or by any method that produces a ciphertext the oracle accepts with HTTP 200).
6. Verifies the forged ciphertext is accepted by the oracle (HTTP 200).
7. Writes results to `/app/output.json`.

### Output (`/app/output.json`)

```json
{
  "recovered_plaintext": "<the original plaintext as a UTF-8 string>",
  "forged_ciphertext_hex": "<hex string of the forged ciphertext that the oracle accepts>",
  "forged_plaintext": "<the full new plaintext string, i.e. forge_prefix + original plaintext>",
  "oracle_accepted": true
}
```

- `recovered_plaintext`: the decrypted original message as a readable string (padding bytes removed).
- `forged_ciphertext_hex`: lowercase hex encoding of the forged ciphertext bytes.
- `forged_plaintext`: the full concatenated plaintext before padding.
- `oracle_accepted`: boolean, must be `true` — confirmed by sending the forged ciphertext to the oracle and receiving HTTP 200.

### Execution

1. Start the oracle server: `python3 /app/oracle_server.py &`
2. Run the attack: `python3 /app/attack.py`
3. The attack script must produce `/app/output.json` upon completion.
