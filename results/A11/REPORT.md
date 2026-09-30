# A11 — hardened CLI-Gym grader and base-model headroom (DONE: G1 pass, G2 FAIL)

Question: with a grader that cannot be gamed, does the prompted base Qwen3.5-9B fail CLI-Gym repair tasks often
enough, and inconsistently enough, for RL to have something to learn? Registration: `PREREGISTRATION.md` A11,
A11.1-A11.5. No training here.

## Grader v2

A run passes only if (b) every code file the task's Dockerfile added, changed or deleted is back to the healthy
("gold") image's version (byte-identical, or AST-identical for Python), (c) no start-up hook exists that gold
lacks (`.pth`, `sitecustomize`, `/etc/ld.so.preload`), and (a) the task's tests pass after the test-side files
have been made identical to gold. (b) and (c) are read before (a) touches anything.

## Gate G1 (grader validation on A10's 18 audited tasks): PASS

| | Dataset grader (v1) | Grader v2 |
|---|---|---|
| Wrong-output controls accepted | 18 of 18 | **0 of 18** |
| References passing twice | 18 of 18 | 15 of 18 |

The 3 references that fail v2 fail only part (b), because the damage cannot be undone offline: 261 glibc
conversion modules overwritten with random bytes, a Python binary whose backup needs a secret that is not in the
container, and a library source file shredded with no copy left. Those tasks leave the pool as infeasible.

Honest caveats: v2's rules were adjusted twice after seeing G1 output (A11.5: count added/deleted *code* only,
after a correct repair failed on deleted `.gitignore`/`.github` files; and a merged-`/usr` path fix so a
helper package's library was not counted as damage). The pre-A11.5 run is kept in `g1_before_A11.5/`. Because of
that, the held-out validity check is moved to the headroom run: every v2 pass is read by an independent reviewer.

## Headroom run (48 tasks x 4 attempts; gate G2: FAIL)

| | v1 (dataset grader) | v2 |
|---|---|---|
| Mean pass rate (46 graded tasks) | 0.424 | **0.168** |
| Tasks 0/4 | | 35 |
| Tasks mixed (1-3 of 4) | | **5** (gate needs >= 12) |
| Tasks 4/4 | | 6 |

- G2 requires >= 12 mixed tasks and a mean in [0.10, 0.70]. The mean is in range; mixed is 5. Even counting the
  two harness-failed tasks as mixed gives 7, so the failure is not an artefact of exclusions.
- Two tasks are excluded as harness failures, not model failures: one replaces `/bin/sh` (the sandbox's own
  start-up shell) and one corrupts the dynamic-linker cache the harness needs; all their attempts ended before
  the model ran a command. One candidate whose `task.yaml` does not parse was replaced, as registered.
- 47 attempts pass the dataset grader but fail v2. Every one inspected is a shortcut or partial repair (in one
  task the model never touched the damaged file; in another it left the injected library on disk).
- **Reading:** with a trustworthy grader the prompted 9B mostly fails, and when it succeeds it succeeds
  consistently. That is the opposite of X1 (base already solved nearly everything) with the same consequence:
  plain RL from the base has almost no within-task variance to learn from.

## Registered consequence

Stop before any RL design on this basis. The natural next step is SFT first (demonstrations of correct repairs),
then measure headroom again from the SFT model; that needs its own registration and an owner decision.
