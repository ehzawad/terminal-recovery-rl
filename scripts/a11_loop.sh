#!/bin/bash
# A11 headroom loop: grade the batch just run, free its images (keeping images the next candidates need), run the next batch.
set -u
cd "$(dirname "$0")/.."
PY=/mnt/sdb/arafat/ehz/llm/.venvs/rl/bin/python
free_images() {
  L=$($PY scripts/a11_free_images.py); [ -n "$L" ] && sg docker -c "docker image rm $L" >/dev/null 2>&1; true
}
for N in 16 24 32 40 48; do
  nice $PY scripts/a11_grade.py --episodes --jobs 4 >> runs/a11_grade_loop.log 2>&1
  free_images
  U=$($PY -c "import json;print(sum(v.get('usable',False) for v in json.load(open('results/A11/tasks.json')).values()))")
  [ "$U" -ge "$N" ] && continue
  nice $PY scripts/a11_headroom.py --max-tasks $N --tasks-parallel 2 >> runs/a11_headroom_loop.log 2>&1
done
nice $PY scripts/a11_grade.py --episodes --jobs 4 >> runs/a11_grade_loop.log 2>&1
free_images
echo A11_LOOP_DONE >> runs/a11_headroom_loop.log
