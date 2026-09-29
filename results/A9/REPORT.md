# A9 audit of new data (first batch: 24 SETA, 16 TMax, 8 LiteCoder)

Registered procedure: PREREGISTRATION.md (A9, A9.1). Seeded sample: `results/A9/sample.json`.
Nothing from this batch enters training. The headroom gate was not run.

## Verdict against the registered triage rule

Admissible = builds offline, no-op fails, reference passes in two fresh containers, wrong-output control fails,
independent blind review says valid, safety ok, no confirmed answer exposure. Infeasible and unverified count as not admissible.

| dataset | n | admissible | reviewer valid | reference passes 2x | wrong-output control accepted | confirmed exposure |
|---|---|---|---|---|---|---|
| SETA | 24 | 1 (4%) | 4 | 20 | 17 | 2 |
| TMax | 16 | 0 (0%; 0/5 of the verifiable subset) | 1 | 4 (of 5 with a recorded success) | 10 | 4 |
| LiteCoder | 8 | 1 (12%) | 2 | 4 | 3 | 1 |
| all | 48 | 2 (4%; Wilson 95% [1%, 14%]) | 7 | 28 | 30 | 7 |

Registered rule: at most 25% admissible means drop. Result: 4%, so drop these three datasets as training sources.

Sensitivity (no other reading changes the call except dropping most criteria):
- ignore the wrong-output control: 7/48 = 15% (Wilson upper bound about 28%, so this reading alone would touch the owner-decides band);
- also ignore the blind review verdict: 24/48 = 50%;
- treating TMax unverified as pass and ignoring reference failures: 38/48 = 79% (an upper bound that ignores every quality criterion).

## What is actually wrong

- **Graders are weak.** 58 confirmed weak-grader findings. The wrong-output control (a partial or hard-coded solution written blind by an
  Opus reviewer) was accepted in 30 of 48 tasks. Most graders test fixed inputs by substring or exact value, so stubs pass. Spot checks
  of accepted controls (SETA ask_ubuntu 1050, so 11563963, so 2885173, unix_linux 82598, LiteCoder rsa) confirm the controls really violate the stated requirement.
  Caveat: a hard-coding adversary is a strict bar; the partial-fix controls are the more convincing evidence.
- **Exposure.** 7 tasks: expected results or answer baked into agent-visible files (SETA so 74892964, ask_ubuntu 227; TMax 005524, 003160, 002330, 004748 (setup data with secrets left in /tmp); LiteCoder crosslingual labels).
- **Offline infeasibility.** 4 LiteCoder ML tasks: reference and verifier pip-install numpy/sklearn/torch at run time (not baked in the image). SETA 74892964 needs a working Java gateway; SETA 276927 timed out at 600 s; SETA 927 fails its own end-to-end test from a stale SSH master socket.
- **TMax has no reference solutions** (0 of 14,601 nonempty). Only 6,174 of 14,601 have at least one recorded successful Gemini-3-flash rollout; 11 of our 16 samples had none, so they are unverified (not defective, but not admissible). Every container.def uses network in %post (expected for builds); 5,136 reference /gpfs paths.
- **Confirmed defect types (reviewer, with quoted evidence):** weak_grader 58, unstated_requirement 11, overstrict_grader 11, ambiguity 12, network_or_gpu 12, contradiction 8, answer_exposure 7, nondeterminism 2, other 10.

## Harness notes (bugs fixed during the audit, all before final numbers)
- LiteCoder Dockerfile stripping removed the base apt-get layer (regex matched asciinema in the same RUN); fixed, all 8 LiteCoder tasks re-run.
- Canary tasks were re-run with `--mutants-only` after mutant scripts were written.
- Not done: the optional 4-attempt Qwen preview on admissible tasks (only 2 admissible; not informative).

## Files
`scripts/a9_draw.py`, `a9_audit.py`, `a9_static.py`, `a9_aggregate.py`; `results/A9/records/`, `reviews/` (blind), `mutants/`, `static_screen.json`, `summary.json`.
