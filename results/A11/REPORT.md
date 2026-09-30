# A11 — hardened CLI-Gym grader and base-model headroom (IN PROGRESS)

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

## Headroom run (batch 1 of 6: 8 tasks x 4 attempts)

| | v1 passes | v2 passes |
|---|---|---|
| 32 attempts | 13 | 4 (one task, 4/4) |

- Every v1-only pass inspected so far is a real shortcut: in one task the model never touched the damaged file
  (`gunicorn/sock.py` is absent from its change set) and v1 still passed it 4 of 4 times.
- One borderline case: the model fixed the behaviour but left the injected `libcorrupt_categorical.so` on disk;
  v2 requires injected code to be removed.
- Outcomes are all-or-nothing so far: every task is 0/4 or 4/4, none mixed. Gate G2 needs >= 12 mixed tasks of 48
  and a mean v2 pass rate between 0.10 and 0.70.
