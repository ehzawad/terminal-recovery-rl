#!/bin/bash
# Partial repair: fix only the Python stdlib codec files; leave every glibc gconv module corrupted (mode 000, random bytes, garbage gconv-modules)
E=/opt/miniconda3/envs/testbed/lib/python3.10/encodings
SRC=$(ls -d /opt/miniconda3/pkgs/python-3.10.*/lib/python3.10/encodings | head -1)
for f in utf_8 latin_1 iso8859_1 utf_16 utf_32 ascii; do cp "$SRC/$f.py" "$E/$f.py"; done
