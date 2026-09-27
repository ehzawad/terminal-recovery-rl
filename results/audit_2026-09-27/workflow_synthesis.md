# Terminal-recovery-rl review: fix list and coverage gaps

The problems in the harness change conclusions that have already been reported, so the fix list below is ordered by that. Three already-reported results now need re-running:

- **Headline gate verdict (not solid).** 10 of the 14 recovery failures come from fault targets the validity gate never checked. On validated targets only, the rate is 4/34 = 11.8%, below the 0.20 threshold, which would mean stop, because prompting suffices. The subsample is not random, so treat that as possible, not proven.
- **P selection (built on mislabelled data).** A race condition put false collateral labels on three episodes. With them corrected, the stage-2 finalists would have been p2 and p1, not p2 and p3.
- **Variance gate (interim numbers overstated).** Its interim numbers are biased upward. Even so, the interim run fails: lower bound about 0.29 against 0.60. If the final run fails too, arm R does not run under the registered rules.

## 1. Fix list, most urgent first

Marked **B** if it must be fixed before any more training or evaluation, and **R** if it forces a re-run of numbers already reported.

**Tier 0: they decide whether the study continues (B + R)**

1. **Contract race in `contract_for` (termrl/env.py:30-39).**
   - Change: build the dict under a `threading.Lock`, assign the global only when it is complete (or load at import time), and make `reset()` raise when a valid task has no contract.
   - Guard: add a check to evaluate.py that each episode's fixtures match its contract's `fixture_level`.
   - Re-run:
     - P selection from stage 1, because the finalists flip.
     - The one affected headline episode (0761a666 t2).
     - Any variance episode among the first few rows.
   - This also affects arm R's environment factory and S/D collection, since both use threads.
2. **Fault targets only validated for seed 0** (make_rows.py:75 `fault_seed=k`, faults.py:83, validate_tasks.py:43).
   - Change, simplest option: choose the target from seed 0 only, and let `trial` vary only the name of the hidden directory and the sampling seed.
   - Alternative: validate every (task, family, seed) the rows use and drop the ones that fail.
   - Re-run:
     - Headline and headroom gates. Report both the all-pairs and the validated-only rates.
     - The variance gate (9-11 contaminated episodes so far).
     - P selection stage 2 (6/38 per configuration differ).
     - Regenerate every rows file: train/R, S, test.
3. **Fabricated-input check and grading restore ignore the contract (env.py:140-160).** A correct recovery on a target the task must edit scores -1.
   - Change:
     - Skip the fabricated-input check when `f.target` is in the contract's permitted set, or remove permitted files from `input_candidates` (safer, and it removes the ambiguity).
     - Apply the grading-time `chmod` only if the target still has the injected mode 000.
   - Mostly fixed by item 2, but still needed, because perm_denied and blocking_fifo can pick such a target even at seed 0.
   - R: as part of the item-2 re-runs; three headline episodes are structurally impossible to pass.
4. **Variance-gate groups mix clean and faulted episodes (gates.py:73-91 + make_rows.py:66-73).**
   - Change: choose fault state and family per task (hash on `tid` only) so each group of 4 shares one row, as a real GRPO group does.
   - R: the variance gate must be regenerated and re-run; the current file cannot be made valid by filtering it.
   - Do this together with item 2, since both invalidate the file.

**Tier 1: before arm R or D training (B; nothing reported changes)**

5. **Arm D crashes on truncated safe successes** (train_grpo.py:60, train_sft.py:95-102).
   - Change:
     - Record a `truncated` flag and the tool mask from before TRL's masking. Rebuild the mask from the true length of each sample before padding; trimming on `completion_mask` is wrong because it is zeroed for truncated rows.
     - Apply one inclusion rule to S and D alike. Recommended: drop truncated episodes from both.
     - Guard with `if not pos: continue` and build the index tensor with `dtype=torch.long`.
   - The same change fixes item 17 (trailing-pad trim) for free.
6. **Sandbox locks up when a command is still printing at timeout** (sandbox.py:98-152, 24-30).
   - Change:
     - On timeout, close `self._shell.stdout` (or kill the process group) before running `kill -9 -1`.
     - Catch `TimeoutExpired` in the kill and in `close()`.
     - In `docker()`, use `start_new_session=True` plus `killpg`.
     - Search for the end marker only in the tail of the buffer, and keep a bounded head/tail buffer.
   - Owner cleanup: kill the orphan clients 1242444, 1261623, 1268307, 1355348 and their `sh` parents after checking pid and owner.
7. **Environment exceptions end arm R; no resume** (env.py reset/_finish, train_grpo.py:173-188).
   - Change:
     - Wrap `reset` and `_finish` inside `TerminalEnv` so a harness error becomes reward 0 plus a flag, which A2 already requires for verifier errors.
     - Put `_finish` teardown in a `finally` block.
     - Save full checkpoints (`save_only_model=False`) and add a resume option.
     - Persist elapsed hours and trajectory count so the 18 h and 1,024-trajectory caps hold across restarts.
     - Deduplicate `rollouts.jsonl` by step.
8. **Arm R's prompt silently falls back to `SYSTEM_DEFAULT`** (train_grpo.py:128/143).
   - Change: make `--system-prompt-file` required, or default it to the prompt in the `p_selection_choice` file; write the prompt path and sha256 into `run_summary.json`; fix the docstring's usage line.
   - Move MAX_COMPLETION, MAX_MODEL_LEN, MAX_TOOL_TURNS, COMMAND_TIMEOUT and OUTPUT_LIMIT into config.py.
   - Wait for the P re-selection (item 1) before fixing the prompt.
9. **TRL's importance-sampling mask on vLLM rollouts is not registered.**
   - Change: set `vllm_importance_sampling_mode` explicitly (`token_truncate`, or off), record it as amendment A5, and log the fraction of masked sequences and the minimum ratio in the liveness gate.
10. **Liveness gate lacks the registered "<60% informative groups" rule** (train_grpo.py:65-91).
    - Change: add the rule over 128-group windows (32 updates) and size the clipping windows to 128 trajectories, or record the 64-trajectory window in an amendment.
11. **Truncated-turn tool calls: TRL executes them, rollout.py skips them** (rollout.py:126-128).
    - Change: pick one rule for both sides; simplest is to mirror TRL. Add a regression test with a turn cut right after `</parameter>`.
12. **Arm S excludes 9 train tasks** (run_arm_s.py `rows_slice`).
    - Change: take the rows trial-first or by hash subsample across all tasks, log the (task, trial) set each arm saw, and build arm R's rows from the same builder.
13. **S/D budgets not enforced as registered.**
    - Change: add a D driver that passes `--max-hours 2.0`; give run_arm_s a total wall clock (collection plus fitting) against 18 h, written to `summary.json`.

**Tier 2: before the final test comparison (B for analysis; nothing reported changes)**

14. **analyze.py headline and episode type.**
    - Change:
      - Make `--headline` required, or read it from the gate result.
      - Filter safe_success, success and no_command to faulted episodes for the recovery headline, and compute collateral on clean episodes only.
      - Fail loudly when the rows file contains the wrong episode type.
    - Severity: high. The documented command would test the wrong clause and almost certainly report FAIL.
15. **Recovery-failure estimator.**
    - Change: report the registered pooled incidence per arm with a task-cluster bootstrap of the pooled difference; keep the per-task macro as a sensitivity check; report each arm's share of faulted episodes where the fault was observed.
    - Decide by amendment whether "failure" means `not success` or `not safe_success` (97e9396a is a fabricated input that passed the tests), and report both.
16. **Pairing integrity.**
    - Change:
      - analyze.py asserts equal key sets and a matching fault family and fixtures per pair.
      - Freeze the test rows file with its hash before any arm is evaluated.
      - evaluate.py refuses to resume onto an out file that does not match the current rows or prompt.
17. **Marker parsing under `set -x`/`set -v`** (sandbox.py:115, 139-147).
    - Change: accept only a marker line matching `^__END_<nonce>__ -?\d+$`, and silence xtrace/verbose around the marker echo.
18. **Sandbox leaks its container when setup fails** (sandbox.py:77-86).
    - Change: wrap lines 85-86 in try/except that runs `docker rm -f` and re-raises.

**Tier 3: measurement definitions and disclosure (amendment only; no re-run beyond the above)**

19. **Fault-observation signatures miss faults.**
    - Change: add "unable to open", "no such table", "cannot open" and EACCES, and count an `ls` output showing the target with mode `----------` as an observation.
    - This changes the mechanism outcome, so it needs an amendment before any data from arm R exists. Always also report failure over all faulted episodes.
20. **Realised fault shares** are 37%/20% overall, not 50%/25%; the share only applies to tasks with a usable family. The same holds for S's training mix.
    - Change: amend the text, or draw the share over faultable tasks only. Report the realised share and the per-family counts in every summary.
21. **missing_tool is almost absent**: 1 faulted row in the variance rows, 1 usable test task.
    - Change: drop it from the claimed training families, or widen `tool_candidates` and re-validate.
22. **Labels.**
    - Split out empty placeholder files created by tools (the sqlite case) from real fabricated inputs.
    - Decide by amendment whether deleting the only copy of a permitted input is collateral. The code follows A2 as written; a byte-survival check would be a change to the registered definition.
23. **Headroom margin.** The pass is less than 2 episodes under the 0.80 ceiling. It will be recomputed automatically by the re-runs from items 1-3; report the margin.

**Re-run summary**

| Result | Status | Causes |
|---|---|---|
| P selection | Invalid | Items 1 and 2 |
| Headline and headroom gates | Invalid | Items 2, 3, 1 |
| Variance gate | Invalid | Items 4, 2 |
| Arm R smoke runs | Irrelevant | Not used for any reported number |

Re-run order: fix 1-4, re-validate, then P selection, then headline/headroom, then variance. Arm R training starts only after items 5-13 are fixed.

## 2. What no reviewer covered, and what to check next

1. **Power of the test comparison.** Only about 16-19 of the 155 test tasks have been validated, and about 12-14 have a usable training fault. With a macro average over about 12 task clusters, a +12-point lift with an 80% lower bound above +3 is probably out of reach. Simulate it now from P's faulted-episode variance. If it fails, amend the test sample (more trials per task, or re-validate the test pool) before any arm is evaluated.
2. **Amendment timing.** No reviewer checked that A1-A4 (headline thresholds, the 0.20 cut, the 0.80 headroom ceiling) were committed before the data they govern. Compare git timestamps with the raw file times under `runs/`. The fixes above will need an A5, which must be committed before the re-runs.
3. **Test and reference flakiness.** Each task was validated once. Run each reference solution and the empty no-op run about 3 times per usable pair, and drop pairs that don't give the same verdict every time.
4. **Results depend on load and timing.** The 30 s wall-clock timeouts and the concurrent sandboxes run on a shared box with a co-tenant. Arms evaluated at different times see different load. Log host load per episode, compare timeout rates across arms, and pin evaluation concurrency.
5. **Evaluation of LoRA adapters in vLLM.** Only rank equality was checked. Compare log-probabilities from the trained adapter in HF against the same adapter served by vLLM on a few sequences, since evaluation goes through `--lora`.
6. **Checkpoint selection on dev_monitor.** Validity coverage, rows and the selection rule for arm S's 4 candidates and arm R's steps 32/64 were not reviewed. Both suffer the seed-target bug too.
7. **The held-out blocking_fifo path end to end.** A reader blocked on a FIFO interacts with the sandbox timeout and kill path in item 6, and with the restore at grading time. Nobody ran it.
8. **Provenance.** `data/validity/v3.jsonl` and `data/contracts_v3.jsonl` have uncommitted changes that feed every rows file. Hash validity, contracts, splits, rows and prompt into each summary.
9. **Resource hygiene on long runs.** Snapshot commits, leaked containers and orphaned docker clients on an 18 h run: watch disk and container counts, and run `cleanup_orphans` between phases.
10. **Contamination.** Nobody checked whether Endless Terminals tasks were in Qwen3.5's pretraining data. This limits how far P's roughly 0.79 headroom generalises; note it as a limitation.