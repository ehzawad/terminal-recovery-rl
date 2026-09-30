#!/bin/bash
# A13 unattended chain: wait for the A12 teacher-ceiling run -> teacher on 800 more train tasks -> SFT data -> SFT -> TEST eval.
set -u
cd "$(dirname "$0")/.."
PY=/mnt/sdb/arafat/ehz/llm/.venvs/rl/bin/python
GPU=GPU-4754ca84-fd1d-907b-5c18-7c578d001bda
log() { echo "[$(date +%H:%M)] $*" >> runs/a13_chain.log; }
gpu_free() { [ "$(nvidia-smi --id=$GPU --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 2000 ]; }
log "waiting for the A12 teacher-ceiling run"
until [ "$(ls results/A12/teacher_test/*.json 2>/dev/null | wc -l)" -ge 44 ] && gpu_free; do sleep 60; done
log "teacher on A13 train tasks"
nice $PY scripts/a12_run.py --model teacher --split results/A13/train_tasks.json --attempts 2 --out results/A13/teacher_train --tasks-parallel 6 >> runs/a13_teacher_train.log 2>&1
log "teacher exit $?"
until gpu_free; do sleep 30; done
mkdir -p runs/A13
$PY scripts/a12_build_sft.py --dirs results/A12/teacher_train results/A13/teacher_train --out runs/A13/sft_data.jsonl --stats results/A13/sft_data_stats.json >> runs/a13_chain.log 2>&1
log "SFT"
PYTHONPATH=. CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=$GPU PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True nice $PY scripts/train_sft.py \
  --data runs/A13/sft_data.jsonl --out runs/A13/sft --epochs 1 --save-epochs 1 --lr 1e-4 --lora-r 16 --seqs-per-update 16 \
  --max-len 32768 --max-hours 10 >> runs/a13_sft.log 2>&1
log "SFT exit $?"
[ -d runs/A13/sft/epoch1 ] || { log "no adapter; stopping"; exit 1; }
until gpu_free; do sleep 30; done
log "TEST eval"
nice $PY scripts/a12_run.py --model sft:$PWD/runs/A13/sft/epoch1 --split test --attempts 4 --out results/A13/sft_test --tasks-parallel 3 >> runs/a13_sft_test.log 2>&1
log "A13_CHAIN_DONE exit $?"
