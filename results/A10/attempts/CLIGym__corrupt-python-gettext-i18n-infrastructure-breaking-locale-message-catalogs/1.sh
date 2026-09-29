#!/bin/bash
set -e
cd /testbed
P=/opt/miniconda3/envs/testbed/lib/python3.10
# gettext: restore the real .mo magic numbers (evidence: diff vs /usr/lib/python3.10/gettext.py)
sed -i 's/LE_MAGIC = 0x950412df/LE_MAGIC = 0x950412de/; s/BE_MAGIC = 0xde120494/BE_MAGIC = 0xde120495/' $P/gettext.py
# _strptime: undo rotated weekday/month name tables
sed -i 's/self\.a_weekday = \[a_weekday\[-1\]\] + a_weekday\[:-1\]/self.a_weekday = a_weekday/; s/self\.f_weekday = \[f_weekday\[-1\]\] + f_weekday\[:-1\]/self.f_weekday = f_weekday/' $P/_strptime.py
sed -i 's/self\.a_month = a_month\[1:\] + \[a_month\[0\]\]/self.a_month = a_month/; s/self\.f_month = f_month\[1:\] + \[f_month\[0\]\]/self.f_month = f_month/' $P/_strptime.py
rm -f $P/__pycache__/gettext.cpython-310*.pyc $P/__pycache__/_strptime.cpython-310*.pyc $P/__pycache__/locale.cpython-310*.pyc
# gspread/utils.py was tampered too (git shows it modified): restore tracked version
git checkout -- gspread/utils.py
diff /usr/lib/python3.10/_strptime.py $P/_strptime.py && echo strptime-ok
grep -n "MAGIC = " $P/gettext.py
