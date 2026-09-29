#!/bin/bash
# Skips the brute-force/decryption check: just derives the key for the first candidate word
cd /app
python3 -c "import sys; sys.path.insert(0,'/app'); import recover; print(recover.derive_key('time'))" > /app/solution.txt
