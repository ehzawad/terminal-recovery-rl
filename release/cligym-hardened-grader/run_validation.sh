#!/bin/bash
# Re-run reference (x2) and wrong-answer control for the 18 audited tasks with the released grader.py.
R=$(dirname "$0"); REPO=/mnt/sdb/arafat/ehz/llm/terminal-recovery-rl; PQ=/mnt/sdb/arafat/ehz/llm/.pools/audit10/train.parquet
export DOCKER=$R/testbin/dockerwrap CLIGYM_GRADER_CACHE=$R/cache
mkdir -p $R/validation
run() { k=$1; kind=$2; n=$3; src=$4
  out=$R/validation/${k}__${kind}${n}.json; [ -f $out ] && return
  nice /mnt/sdb/arafat/ehz/llm/.venvs/rl/bin/python $R/grader.py grade --parquet $PQ --task $k --script $src --dataset-grader > $out 2>$out.err; }
for f in $REPO/results/A10/refs/*.sh; do
  k=$(basename $f .sh); k=${k#CLIGym__}; m=$REPO/results/A10/mutants/CLIGym__$k.sh; [ -f $m ] || continue
  ( run $k reference 1 $f; run $k reference 2 $f; run $k control 1 $m
    $DOCKER image rm -f $(python3 -c "import hashlib,pandas as pd;d=pd.read_parquet('$PQ').set_index('task_id').loc['$k'].dockerfile;print('cligym-grader:'+hashlib.sha256(d.encode()).hexdigest()[:16])") >/dev/null 2>&1 ) &
  while [ $(jobs -r | wc -l) -ge 3 ]; do sleep 5; done
done
wait; echo VALIDATION_DONE
