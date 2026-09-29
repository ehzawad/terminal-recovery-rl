#!/bin/bash
# Repair for corrupted Python codecs + glibc gconv configuration.
set -uo pipefail
ENC=/opt/miniconda3/envs/testbed/lib/python3.10/encodings
SYS=/usr/lib/python3.10/encodings
GCONV=/usr/lib/x86_64-linux-gnu/gconv

# 1) Python codec modules were overwritten with "# CORRUPTED" (interpreter cannot even start).
#    The system CPython 3.10 ships byte-identical pure-Python codec modules (other files in the
#    two encodings/ dirs compare identical), so restore the damaged ones from there.
for f in utf_8 latin_1 iso8859_1 utf_16 utf_32 ascii; do
  if ! grep -q 'def getregentry' "$ENC/$f.py" 2>/dev/null; then
    cp -f "$SYS/$f.py" "$ENC/$f.py"
  fi
done
rm -f "$ENC"/__pycache__/*.pyc

# 2) glibc gconv: all modules were chmod 000 -> restore normal permissions.
chmod 644 "$GCONV"/*.so

# 3) Core gconv-modules config was overwritten with a junk line. Rebuild the core (non-extra)
#    config for the modules that are not covered by gconv-modules.d/gconv-modules-extra.conf
#    (ANSI_X3.110, CP1252, ISO8859-1, ISO8859-15, UNICODE, UTF-16, UTF-32, UTF-7).
if ! grep -q '^module' "$GCONV/gconv-modules" 2>/dev/null; then
cat > "$GCONV/gconv-modules" <<'CONF'
# GNU libc iconv configuration (core modules).
# Additional modules are configured in gconv-modules.d/*.conf.
#	from			to			module		cost
alias	ISO-IR-100//		ISO-8859-1//
alias	ISO_8859-1:1987//	ISO-8859-1//
alias	ISO_8859-1//		ISO-8859-1//
alias	ISO8859-1//		ISO-8859-1//
alias	ISO88591//		ISO-8859-1//
alias	LATIN1//		ISO-8859-1//
alias	L1//			ISO-8859-1//
alias	IBM819//		ISO-8859-1//
alias	CP819//			ISO-8859-1//
alias	CSISOLATIN1//		ISO-8859-1//
alias	8859_1//		ISO-8859-1//
alias	OSF00010001//		ISO-8859-1//
module	ISO-8859-1//		INTERNAL		ISO8859-1	1
module	INTERNAL		ISO-8859-1//		ISO8859-1	1

alias	ISO8859-15//		ISO-8859-15//
alias	ISO885915//		ISO-8859-15//
alias	ISO-IR-203//		ISO-8859-15//
alias	ISO_8859-15//		ISO-8859-15//
alias	LATIN-9//		ISO-8859-15//
alias	LATIN9//		ISO-8859-15//
alias	ISO_8859-15:1998//	ISO-8859-15//
module	ISO-8859-15//		INTERNAL		ISO8859-15	1
module	INTERNAL		ISO-8859-15//		ISO8859-15	1

alias	MS-ANSI//		CP1252//
alias	WINDOWS-1252//		CP1252//
module	CP1252//		INTERNAL		CP1252		1
module	INTERNAL		CP1252//		CP1252		1

alias	ISO-IR-99//		ANSI_X3.110-1983//
alias	ISO_6937-2:1983//	ANSI_X3.110-1983//
alias	CSA_T500-1983//		ANSI_X3.110-1983//
alias	CSA_T500//		ANSI_X3.110-1983//
alias	NAPLPS//		ANSI_X3.110-1983//
alias	CSISO99NAPLPS//		ANSI_X3.110-1983//
module	ANSI_X3.110-1983//	INTERNAL		ANSI_X3.110	1
module	INTERNAL		ANSI_X3.110-1983//	ANSI_X3.110	1

alias	CSUNICODE//		UNICODE//
module	UNICODE//		INTERNAL		UNICODE		1
module	INTERNAL		UNICODE//		UNICODE		1

alias	UTF16//			UTF-16//
module	UTF-16//		INTERNAL		UTF-16		1
module	INTERNAL		UTF-16//		UTF-16		1
alias	UTF16LE//		UTF-16LE//
module	UTF-16LE//		INTERNAL		UTF-16		1
module	INTERNAL		UTF-16LE//		UTF-16		1
alias	UTF16BE//		UTF-16BE//
module	UTF-16BE//		INTERNAL		UTF-16		1
module	INTERNAL		UTF-16BE//		UTF-16		1

alias	UTF32//			UTF-32//
module	UTF-32//		INTERNAL		UTF-32		1
module	INTERNAL		UTF-32//		UTF-32		1
alias	UTF32LE//		UTF-32LE//
module	UTF-32LE//		INTERNAL		UTF-32		1
module	INTERNAL		UTF-32LE//		UTF-32		1
alias	UTF32BE//		UTF-32BE//
module	UTF-32BE//		INTERNAL		UTF-32		1
module	INTERNAL		UTF-32BE//		UTF-32		1

alias	UTF7//			UTF-7//
module	UTF-7//			INTERNAL		UTF-7		1
module	INTERNAL		UTF-7//			UTF-7		1
module	UTF-7-IMAP//		INTERNAL		UTF-7		1
module	INTERNAL		UTF-7-IMAP//		UTF-7		1
CONF
fi

# 4) Rebuild the (random-garbage) gconv-modules.cache from the config files.
rm -f "$GCONV/gconv-modules.cache"
/usr/sbin/iconvconfig "$GCONV" || true

# NOTE: 10 module binaries (ISO8859-1/-2/-15, UTF-16/-32/-7, UNICODE, EUC-JP, GBK, BIG5) were
# overwritten with random bytes (dpkg md5sums confirm). There is no offline copy of libc6 to
# restore them from; the fix for that is `apt-get install --reinstall libc6` once online.
# glibc's built-in converters (UTF-8, ASCII, UCS-2/4, INTERNAL) are unaffected.
exit 0
