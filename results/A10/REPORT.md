# A10 — audit of CLI-Gym (IN PROGRESS)

Status as of 2026-09-29: **17 of 24 sampled tasks decided, all 17 not admissible; 7 pending** (waves 3-4).
"Proceed" (>= 50%) is no longer reachable. The dataset is dropped if at most 6 of 24 (25%) are admissible, so it
avoids the drop line only if all 7 remaining tasks are admissible. Registration: `PREREGISTRATION.md`, A10 and A10.1.
Live numbers: `summary.json` (regenerate with `scripts/a10_aggregate.py`).

## Source

`LiberCoders/CLI-Gym` at 552945c5aaf0: 1,655 tasks over 25 SWE-smith repository images, Apache-2.0. Each task is a
healthy ("gold") repository image plus Dockerfile lines that an agent wrote to break it; graded by pytest on a
listed set of test IDs inside the repository. No repair script is released.

## Procedure (per task)

1. Static screen (`static_screen.json`).
2. Build the damaged image (network on); everything else offline, 4 GB, 2 pinned CPUs.
3. Untouched damaged container must fail; gold image must pass twice; an Opus-written repair reference
   (up to 3 counted attempts) must pass twice; a blind reviewer's wrong-output control must fail.
4. Independent blind Opus review (does not see the reference). 5. Safety read.

Sample: 24 tasks, one per repository image, in sha256 order (`sample.json`, `scripts/a10_draw.py`).

## Results so far

| Stage | Tasks failing |
|---|---|
| Build fails (the dataset's own Dockerfile) | 2 |
| Gold image fails the task's own grader | 3 |
| Repair reference could not be written | 0 of 12 attempted |
| Wrong-output control accepted by the grader | 12 of 12 run |
| Blind reviewer: defective | 12 of 12 reviewed |

- **Build failures:** one installs `linux-headers-$(uname -r)` for the host's kernel (10 of 1,655 tasks do this);
  one aborts inside its own openssl encryption loop.
- **Gold failures:** in 2 tasks the listed test IDs contain non-ASCII parameters that pytest cannot find, so the
  run aborts with "no tests ran" even on the healthy image; in 1 (full-suite grader) the healthy repository
  already has a failing test. None of the 3 can ever be passed.
- **Every repair was possible, every grader was weak.** The reference authors repaired all 12 tasks run so far on the first
  attempt, and the harness re-ran each reference twice in fresh offline containers (all pass). But the grader
  accepted a wrong answer in all 12, again confirmed by the harness itself: editing test expectations; a
  `conftest.py` that undoes the damage only during tests; a stub module returning 0; a `sitecustomize.py`
  shadowing the broken stdlib module; a partial repair that leaves the glibc side broken; removing only the
  sabotage the tests can see (TCP interceptor, import hook and a crashing `ssh-keygen` all left in place);
  fixing 2 of 3 injected bugs; a pytest hook that reports every test passed without running it. The root cause is
  structural: the graded tests live in `/testbed`, which the agent can edit, and are not restored before grading.
- **Damage the grader never sees:** several tasks break two things and grade one (the socket interceptor behind
  replayed cassettes, the system libcrypto behind a statically linked binding, a one-byte binary edit that is
  inert), and one encrypted backup needs a secret that is not in the container.
- **Other recurring defects:** titles and instructions describe a different fault than the real one ("seccomp
  profile" is a Python monkeypatch, "PCRE substitution" a patched stdlib file); line-number `sed` edits that
  misfired and shredded source (one task needs the upstream library rewritten from memory); a glibc task whose
  real damage cannot be undone offline and which the grader does not check.
- **Exposure:** 3 flagged. Only one resembles a planted hint (stale pre-damage bytecode); the other two are
  realistic reference copies (Python's own `/usr/lib` stdlib, the conda package cache). Not decisive: each of the
  three is already excluded by an accepted wrong-output control.

## Harness corrections (A10.1, before any reference or review)

Test IDs compared without bash escapes, plus a summary-count rule; full-suite graders handled; containers pinned
to 2 CPUs because `pytest -n auto` started 40 workers in 4 GB and crashed even on a gold image. All base checks
were re-run under the corrected harness.

## Rulings made during the audit

- The reference-author brief forbids deleting conftest files. In the glom task the injected, git-untracked
  `conftest.py` *is* the damage, so deleting it was accepted as a genuine repair (the rule targets tampering
  with the repository's own tests).
- Two references used facts available only from the Dockerfile (a hard-coded byte offset that is also
  discoverable in-container; a decryption secret that is not). Both tasks pass their graded tests without that
  knowledge, and both are already excluded by accepted wrong-output controls.
