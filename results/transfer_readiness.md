# Transfer-study readiness audit (model-free; no Terminal-Bench outcome of any policy)

Pinned sources: TBLite `open-thoughts/OpenThoughts-TBLite` @5c37b41 (Apache-2.0 per its README), Terminal-Bench 2.1
`harbor-framework/terminal-bench-2-1` @7131e43 (Apache-2.0).

## Static inventory (upper bounds, before runtime checks)

| Suite | Tasks | Real reference solution | Reference and instruction need no network | Grader offline as shipped |
|---|---|---|---|---|
| TBLite | 100 | 71 | 57 | 15 |
| TB2.1 | 89 | 85 | 47 | 0 |

- 29 TBLite tasks ship no reference (`solve.sh` prints "no solution written" or is empty), so a grader cannot be
  shown to credit a correct answer; they cannot be admitted.
- 40 TBLite graders pass pytest whatever the task score (the score is written to `/logs/verifier/reward.txt`); the
  harness reads that native reward, never pytest's exit status.
- Every TB2.1 grader installs its dependencies from the network at grading time; all 89 declare
  `allow_internet = true`. Offline use needs grader dependencies staged ahead of time, task by task.

## Runtime trial (termrl/tb.py, scripts/tb_admission.py; offline, images built with network)

| Task | No-op reward | Reference rewards | Admissible |
|---|---|---|---|
| anomaly-detection-ranking | 0.0 | 1.0, 1.0 | yes |
| bash-log-processor-fix | 0.0 | 0.605, 0.605 | no: the reference itself scores 0.605 |
| multi-server-configuration | 0.0 | 0.0, 0.0 | no: no reference solution |

Image builds took about 10 minutes each (apt and PPA installs).

## Serving at long context (results/probe_longctx.json)

vLLM 0.30 on the A6000 at `--max-model-len 32768`, 0.80 utilisation: 8 concurrent 20K-token prompts with
1,024 new tokens each finish in 62 s (2,732 tokens/s in total, about 17 decode tokens/s per stream), GPU
memory 37.6 GiB.

## Implication

The council's transfer design needs at least 80 admitted, lineage-independent external task groups. The
static upper bound is 104 across both suites before any runtime check; 89 of those need offline grader
staging, and the first runtime trial admitted 1 of 3. Reaching 80 is unlikely without relaxing the
admission rules.
