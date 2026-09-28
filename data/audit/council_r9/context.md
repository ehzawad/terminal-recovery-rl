# Council round 9 — terminal-recovery-rl: which open data should train a multi-step Linux terminal agent, and how do we know a dataset is good?

## Owner's questions (verbatim, lightly trimmed)
"The data set we created, how do you know that is a good data set? And the model you build is based on my data set. Is there no data set for Linux terminal command? ... Stack Overflow has [a lot of] data. We could use those to do this RL, right? ... just open source data that is only specifically for Linux terminal command or Linux as a whole."

## Owner decisions just made (picker)
- Model goal: **multi-step Linux terminal agent** (explore, run several commands, recover from errors, finish a task safely) — the current design — not single-command NL→bash translation.
- The exploratory adapter now training (below) should finish and be published as experimental.
- **CC BY-SA 4.0 is acceptable** for public artefacts (Stack Exchange / Stack Overflow derived data), with attribution and share-alike.

## Project state
- Model: Qwen3.5-9B instruct (rev c202236235, hybrid Gated DeltaNet), LoRA r16, one RTX A6000 48 GB; TRL GRPO with environment_factory + colocated vLLM; measured 34.5 s per trajectory, 39.2 GiB peak for 16-command ET episodes; vLLM 32K serving works (8×20K prompts in 62 s).
- Harness (public: huggingface.co/datasets/ehzawad/terminal-recovery-bench): docker sandbox, no network, persistent bash, hidden-test grading with a trusted toolchain, property-level safety oracle with planted user files, deterministic fault injection (unreadable/moved/FIFO input), optional command budget; also an offline runner for Terminal-Bench-style tasks reading the native reward.
- Training data so far: **Endless Terminals** (obiwan96/endless-terminals @26ecf784, MIT; arXiv:2601.16443): 2,492 synthetic Linux file/data tasks, each with an instruction, Dockerfile, hidden pytest and reference solution, plus o3 16-run success rates. We audited 609 (o3 ≥12/16 + static screens) → 593 valid; the o3 ≤11/16 tail: 171 candidates → 84 admissible after a mutation test (20 graders accept wrong output) and an 8-reviewer instruction–test review (68 excluded: 34 unstated tested requirements, 25 contradictions, 20 exposed answers, 5 other).
- Three registered RL studies stopped before training: a good system prompt already solves the valid ET tasks (safe success ~0.78–0.88) and recovers from any fault it names; the hard tail is mostly spec defects; Terminal-Bench offline transfer infeasible (29/100 TBLite tasks lack references; ≤104 offline-feasible candidates across TBLite+TB2.1).
- Now running (owner-requested, exploratory X1): one LoRA Dr.GRPO run (64 updates, 1,024 trajectories) on 256 ET train configs (half of faultable ones faulted), prompt p6, 16 commands; checkpoint on dev_monitor; one test comparison vs the prompted base; published as experimental. The pilot data (variance probe) showed only 25–50% of GRPO groups informative — the prompted base already solves most ET tasks.

## Known open data (for the council to verify, extend and judge)
- Executable multi-step agent datasets: Endless Terminals (2,492, MIT); SETA (camel-ai/SETA-Env, ~4,567 records / ~3,465 source roots, from StackOverflow/Unix questions with evolution variants); TMax-15K (allenai/TMax-15K, 14,601 tasks; some expose answers under agent-visible paths per our earlier audit); LiteCoder-Terminal (arXiv 2605.29559); Terminal-World (2605.20876); skill-graph synthesis (2604.25727); Environment Evolution for Terminal Agents (2609.04128); Terminal-Bench 2.x and TBLite (evaluation).
- Non-executable command data: NL2Bash (~9.3k English→bash pairs from Stack Overflow etc.), NLC2CMD (NeurIPS 2020), InterCode-Bash (execution-based subset of NL2Bash), tldr-pages (CC-BY 4.0), Unix & Linux Stack Exchange / Stack Overflow dumps (CC BY-SA 4.0), man pages.
- RL needs a verifiable reward: an environment where the agent acts and an automatic checker. Q&A text has neither without a conversion pipeline.

## What the owner needs
A clear answer to "how do we know a dataset is good", and a concrete, honest plan for which open data to use next for the multi-step agent (RL and/or SFT), including whether Stack Overflow / Unix.SE can feed RL and how.
