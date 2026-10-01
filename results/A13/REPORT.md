# A13 — five times more teacher demonstrations, SFT again (G3: FAIL; no gain over A12)

Registration: `PREREGISTRATION.md` A13. Same TEST set, prompt, harness and grader v2 as A12.

## Data and training
Teacher (Qwen3.5-27B-FP8) on 800 more train tasks: 651 usable, 299 of 1,302 attempts pass v2 (23%, the same
rate as A12). Combined with A12: **371 verified repairs on 222 tasks** (A12 used 72 on 43). SFT from the base
weights: LoRA r16, lr 1e-4, **1 epoch**, 16 sequences per update (24 updates, 3.6 h on the A6000), max 32K
tokens (median sequence 9.8K, peak memory 42.6 GiB).

## Held-out result (42 TEST tasks; one more TEST task became vacuous on rebuild)

| | Mean v2 pass rate | Mixed tasks (1-3 of 4) |
|---|---|---|
| Base 9B | 0.113 | 5 |
| SFT A12 (72 demos, 2 epochs) | 0.185 | 5 |
| **SFT A13 (371 demos, 1 epoch)** | **0.167** | 6 |
| Teacher 27B (ceiling) | 0.274 | 9 |

Paired, task-level bootstrap 95% CIs:
- A13 vs base: **+0.054 [-0.012, +0.131]** (better on 5 tasks, worse on 2)
- A13 vs A12: **-0.018 [-0.077, +0.036]** (better on 3, worse on 5)
- A12 vs base (same 42 tasks): +0.071 [0.000, +0.149]

## Reading
- Both SFT rounds point the same way (+5 to +7 points over the base), but neither interval clearly excludes
  zero. Five times more data produced no measurable improvement over the first round; the comparison is
  confounded by the registered change to 1 epoch, and 42 tasks x 4 attempts cannot resolve differences of a
  few points.
- **G3 fails again** (6 mixed, needs 12). Even the 27B teacher has only 9 mixed tasks: all-or-nothing outcomes
  look like a property of these tasks, not only of the 9B.
- Train and test share repositories; this is transfer across damage types within the same projects.
