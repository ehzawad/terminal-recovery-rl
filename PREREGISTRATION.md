# Pre-registration — does outcome RL teach Qwen3.5-9B to recover from terminal faults?

Registered 2026-09-26, before any model has been run on a sealed-test task and before any
training. Design reconciled over two codex-council rounds (records: `data/audit/`). Any later
change is appended as a dated amendment below; nothing above the amendments is edited.

## Question

On one 48 GB RTX A6000, with a LoRA adapter, does outcome-based RL on
`Qwen/Qwen3.5-9B` (instruct, revision `c202236235`) improve **recovery from environment faults
in a bash harness** beyond three competitive non-RL alternatives, and is the improvement
visible in the traces as fewer unrecovered faults, not only as a higher score?

## Environment (harness v2, frozen for every arm)

- Tasks: Endless Terminals (obiwan96/endless-terminals @ `26ecf784`), restricted to the 609
  task ids audited in `data/audit/endless_recommended_ids.json`.
- Each task image is built on `termrl-et-base:v1`; the agent is uid 1000, owns `/home/user`,
  has no network, 1 CPU, 2 GB RAM, 256 pids.
- One tool, `bash` (persistent shell, stdin `/dev/null`, 30 s command timeout, 3,000-character
  head+tail output cap). Episode ends when a reply has no tool call, after 16 tool turns, or
  when the 6,144-token completion / 8,192-token context budget is spent. Thinking disabled.
- Grading: the hidden `test_final_state.py` runs after the agent stops, in a fresh container
  from a snapshot of the agent's filesystem, with read-only tests and a read-only trusted
  Python/pytest, `/etc/ld.so.preload` masked, 20 s per test.
- Evaluation decoding: temperature 0.7, top-p 0.95, top-k 20, per-trial seed
  `sha256(task:trial)`. Training rollouts: temperature 1.0.

## Faults

Injected as root before the agent's first turn, on an input file named in the instruction:
`perm_denied`, `moved_input`, `missing_tool` (training families) and `blocking_fifo`
(**held out**: never used in training, demonstrations, prompt selection or reward tuning).
A (task, fault) pair is usable only if the reference solution fails after the fault and passes
after a generic repair (`scripts/validate_tasks.py`, results in `data/validity/`). A task is
usable only if the reference passes and a no-op fails.

## Partitions

`data/splits_v1.json`: `sha256('termrl-split-v1:'+id) mod 16` → train (8/16), dev_search
(2/16), dev_monitor (2/16), test (4/16); the 9 tasks already seen in probe v1 are dev_search.
The unit is the task id; the pool has no verified lineage metadata (audit, §root-count caution),
so independence is a stated limitation. Test outcomes stay sealed until every checkpoint and
configuration is frozen.

## Arms (all start from the same instruct weights and share harness v2)

- **P** — the instruct model with the prompt/controller chosen on dev_search from 8 frozen
  candidate prompts (including an inspect–act–verify prompt, an explicit recovery prompt and a
  termination prompt) plus a verifier-free check-and-revise controller. The selected
  configuration is then used for **every** arm.
- **S** — two rounds of self-generated, verifier-filtered multi-turn rejection-sampling SFT,
  same training tasks, same 1,024-attempt and 9.5 GPU-hour allowance as R, same LoRA capacity;
  checkpoint chosen on dev_monitor from two scheduled candidates.
- **D** — SFT from the instruct weights on every verified success R collected, same SFT recipe,
  two-hour fit, same checkpoint-selection opportunity.
- **R** — LoRA RL (TRL GRPOTrainer, Dr.-GRPO loss, beta 0, group size 4, 4 groups per update,
  no std scaling), reward `0.5·success + 0.5·fraction of hidden checks passed`, at most 32
  updates / 1,024 attempted trajectories / 9.5 GPU-hours; checkpoint chosen on dev_monitor.

S is trained before R.

## Outcomes

- **Primary:** complete binary success within the budget, macro-averaged over test tasks, on
  episodes carrying one training-family fault drawn deterministically per (task, trial).
- **Mechanism:** recovery-failure incidence — among faulted episodes in which the fault was
  observed in a tool output, the fraction that end with the task failed.
- **Secondary:** the held-out `blocking_fifo` family on test tasks; clean (unfaulted) test tasks
  as a retention check; pass^4 per task; tokens, turns and time per episode.

## Gates (automatic; no further owner decision needed to stop)

1. Validity and systems: every admitted pair passes the validity gate; one real training step
   below 44 GiB peak with finite gradients and a verified adapter sync; ≤2 GPU-hours bring-up.
2. Headroom: the strongest non-RL configuration's dev success lies in 20–80% with its upper
   task-cluster 95% bound below 90%, and the named recovery failure occurs in ≥20% of eligible
   opportunities. Otherwise stop before R and report that prompting/SFT suffices.
3. Variance: on up to 128 train tasks × 4 instruct rollouts, the Wilson 95% lower bound on the
   share of groups with differing semantic reward exceeds 60%, and ≥20% of groups contain both
   complete successes and failures. Otherwise stop; no silent change of group size or start point.
4. Training liveness: stop for 3 consecutive updates with no usable gradient, >5% clipping in two
   windows, <60% informative groups in two windows of 128, or non-finite values.
5. Pilot decision: R is reported as beating the controls only if it exceeds each of P, S and D by
   ≥12 points on the primary outcome with every paired task-cluster bootstrap 80% lower bound
   above +3 points, recovery-failure incidence falls by ≥10 points, and a blind audit of R's wins
   finds no verifier exploit. Otherwise the result is reported as negative or inconclusive.

## Claim tier

Single-seed pilot on this slice. The pool cannot supply the ~256 additional independent roots a
confirmation stage needs, so no confirmatory claim is made; transfer to other terminal benchmarks
and absence of general capability regression are not claimed.

## Amendments

**A1 — 2026-09-26, before any dev_search/test run under harness v2.** Operational details fixed
before data:
- Every arm is evaluated with the token-level loop in `termrl/rollout.py`, which renders prompts,
  parses tool calls and appends tool results with TRL's own functions, so evaluation, SFT data and
  RL rollouts share byte-identical sequences. (The earlier chat-API client is retired; probe v1 was
  run with it and is exploratory only.)
- P selection: dev_search tasks with a usable training-family fault are halved by
  `sha256('psel:'+id)`. Half A: all 8 prompts × 1 trial; the two best by macro success (ties →
  lower mean tokens) go to half B with and without the check-and-revise controller × 2 trials; the
  best of those 4 is P. Faults as in the primary outcome; decoding as for evaluation.
- Variance gate sample: up to 128 train tasks with a usable training-family fault × 4 rollouts of
  P at the RL sampling distribution (temperature 1.0, top-p 1.0, no top-k).
- S: round 1 = 512 attempts of P on train rows at the RL sampling distribution, SFT from the
  instruct weights on the successes; round 2 = 512 attempts of the round-1 model, SFT from the
  instruct weights on the union of both rounds' successes (expert iteration). LoRA r16, lr 1e-4,
  2 epochs, 16 sequences per update; candidates = end of epoch 1 and 2 of each round, chosen on
  dev_monitor.
