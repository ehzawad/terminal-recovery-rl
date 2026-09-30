# A12 — SFT first, then re-measure headroom (G3: FAIL)

Registration: `PREREGISTRATION.md` A12. Base Qwen3.5-9B vs the same model after LoRA SFT on verified teacher
repairs; held-out CLI-Gym TEST tasks, prompt p7, grader v2, 4 attempts per task.

## Teacher data
Qwen3.5-27B-FP8 (same tokenizer and template, checked token by token) on 200 drawn training tasks: 154 usable
(the rest fail to build, fail gold, or are vacuous under the new no-op check), **72 of 308 attempts pass v2**
(23%), covering 43 tasks. All 72 were used (at most 2 per task). SFT: LoRA r16, lr 1e-4, 2 epochs, 8 sequences
per update (18 updates, 1.2 h on the A6000), loss 0.21 -> 0.155.

## Held-out result (42 TEST tasks usable on rebuild)

| | Base | SFT |
|---|---|---|
| Mean v2 pass rate | 0.113 | **0.185** |
| Tasks 0/4 | 34 | 32 |
| Mixed (1-3 of 4) | 5 | 5 |
| Tasks 4/4 | 3 | 5 |

Paired difference **+0.071, 95% CI [0.000, +0.149]** (task-level bootstrap); SFT better on 7 tasks, worse on 2.
Two of the 44 frozen TEST tasks became unusable on rebuild (one vacuous under the no-op check; one gold image
now fails its own grader) and are excluded from both columns.

**G3 fails**: the mean did not regress, but only 5 TEST tasks are mixed (needs >= 12). SFT made the model
more capable without making its outcomes less all-or-nothing. Train and test share repositories, so this is
transfer across damage types within the same projects.
