---
license: apache-2.0
pretty_name: CLI-Gym under a hardened grader
language:
- en
tags:
- cli
- terminal
- agents
- reinforcement-learning
- benchmark-audit
- reward-hacking
size_categories:
- n<1K
---

# CLI-Gym under a hardened grader

[CLI-Gym](https://huggingface.co/datasets/LiberCoders/CLI-Gym) (1,655 tasks) builds environment-repair tasks by
taking a healthy repository image and breaking it with Dockerfile commands; an agent must repair the
environment, and pytest checks the result. This repository contains an audit of how far that check can be
trusted, a stricter grader (`grader.py`), and what a 9B model actually achieves once grading is honest.

**Main finding: the dataset's own check accepts a wrong answer in every audited task that has a working repair
(18 of 18), and most of a 9B model's passes under it are shortcuts.**

## 1. Audit of the dataset's grading (24 tasks, one per repository image)

| | Tasks |
|---|---|
| Image does not build (the task's own Dockerfile fails) | 2 |
| Gold image fails the task's own tests (can never pass) | 3 |
| A working reference repair exists (verified twice in fresh offline containers) | 18 of 18 attempted |
| **The dataset's grader also accepts a wrong answer** | **18 of 18** |
| Usable as-is for training | **0** |

One sampled task was not audited to completion. Wrong answers the dataset's grader accepts include: editing the
test expectations; a `conftest.py` or `sitecustomize.py` that undoes the damage only while pytest runs; a pytest
hook that reports every test as passed without running it; removing only the part of the damage the listed
tests exercise (leaving, for example, a malicious import hook or a crashing `ssh-keygen` in place); and stub
modules. The root cause is structural: the graded tests live inside the repository the agent can edit, and are
not restored before grading. Independent review also found recurring task-text problems: titles and
instructions describing a different fault from the real one (a "seccomp profile" that is a Python monkeypatch,
"PCRE substitution" that is a patched stdlib file), line-number `sed` edits that misfired and shredded source,
and planted "recovery hints" that are decoys or need secrets absent from the container. Per-task details:
`audit/tasks.json`; reference repairs and wrong answers: `audit/reference_repairs/`, `audit/wrong_answers/`.

## 2. The hardened grader

A run passes only if all three hold:

1. **Damage undone.** Every code file the task's Dockerfile added, changed or deleted relative to the gold image
   is back to gold (removed if added; byte-identical, or AST-identical for Python, otherwise; same permissions).
   Files of packages the Dockerfile installed as tools, `.git`, and the conda package cache are ignored.
2. **No new start-up hooks.** No `.pth`, `sitecustomize.py` or `usercustomize.py` that gold lacks, and
   `/etc/ld.so.preload` as in gold.
3. **Tests pass on gold tests.** Every test-side file under `/testbed` is made identical to gold, then the task's
   own pytest IDs must all pass.

Checks 1 and 2 read the container exactly as the agent left it.

**Validation on the 18 audited tasks (re-run with the released `grader.py`):**

| | Dataset grader | Hardened grader |
|---|---|---|
| Wrong answers accepted | 18 of 18 | **0 of 18** |
| Reference repairs accepted (both runs) | 18 of 18 | 15 of 18 |

The references the hardened grader rejects fail check 1 only, because the damage cannot be undone exactly
without network access: glibc conversion modules overwritten with random bytes, a Python binary whose encrypted
backup needs a key that is not in the container, and a library source file shredded with no copy left. Such
tasks are not exactly repairable offline and should be excluded from training. Per-run detail:
`validation/grader_validation.json`.

## 3. What a 9B model achieves

Qwen3.5-9B (instruct), system prompt `system_prompt.txt`, a single `bash` tool, at most 30 commands, 32K
context, offline container (2 CPUs, 4 GB), 4 attempts per task on 46 further CLI-Gym tasks:

| | Dataset grader | Hardened grader |
|---|---|---|
| Mean pass rate | 0.424 | **0.168** |

47 attempts pass only the dataset's grader. In one task the model never touched the damaged file and still
passed all 4 attempts. An independent review of all 31 hardened passes found **23 genuine root-cause repairs, no
test edits or test-only workarounds**, and 8 passes from 2 tasks whose damage has no effect (the untouched
container already passes, so those tasks are vacuous; an untouched-container check removes them).

**Supervised fine-tuning on verified repairs.** A larger model of the same family (Qwen3.5-27B-FP8) made 2 attempts on
each of 805 usable tasks (of 1,000 drawn, disjoint from all evaluation tasks); its attempts that pass the hardened grader were used to fine-tune the 9B (LoRA rank 16). On
42 held-out tasks, 4 attempts each, hardened grader:

| | Mean pass rate | Tasks with mixed outcomes (1-3 of 4) |
|---|---|---|
| Qwen3.5-9B | 0.113 | 5 |
| + SFT, 72 verified repairs (2 epochs) | 0.185 | 5 |
| + SFT, 371 verified repairs (1 epoch) | 0.167 | 6 |
| Qwen3.5-27B-FP8 (the demonstrating model) | 0.274 | 9 |

Paired differences with task-level bootstrap 95% intervals: 72-repair SFT vs base **+0.071 [0.000, +0.149]**;
371-repair SFT vs base **+0.054 [-0.012, +0.131]**; 371 vs 72 repairs -0.018 [-0.077, +0.036]. Fine-tuning points
to a gain of 5-7 points, but neither interval clearly excludes zero, and five times more demonstrations gave no
measurable further gain. Held-out and training tasks share repositories (different damage), so this measures
transfer within the same projects.

**Implication for reinforcement learning.** Outcomes are nearly all-or-nothing per task for every model,
including the 27B: at most 9 of 42 tasks show mixed results across 4 attempts. Group-based RL learns from tasks
where some attempts succeed and others fail, so on this task source, at this scale, there is very little
signal to learn from. Per-task numbers: `model_results/`.

## Usage

```bash
pip install pandas
huggingface-cli download LiberCoders/CLI-Gym train.parquet --repo-type dataset --local-dir .
python grader.py grade --parquet train.parquet --task <task_id> --script my_repair.sh --dataset-grader
```

This builds the task image (network needed for the build only), starts a fresh offline container, runs the
script inside it as root in `/testbed`, and prints both verdicts as JSON; the exit status is 0 for a hardened
pass. To grade an agent, run it inside a `Container` and call `grade(container, task, damage_set(task))`.
Set `DOCKER="sudo docker"` if needed. The first grade of a task compares the gold and damaged images, which takes
a few minutes; the result is cached.

## Limitations

- Small samples: 24 audited tasks, 46 and 42 tasks for the model results; intervals are wide.
- Reference repairs, wrong answers and reviews were written by automated agents and verified by execution; the
  reviews are judgments and are included verbatim for checking.
- "Damage undone" assumes repairing means restoring the gold state of the files the damage touched. A different
  but valid fix to the same file fails unless it is AST-identical; a fix elsewhere that leaves the damaged file in
  place also fails. Both are deliberate.
- Two tasks break the runtime a harness needs (`/bin/sh`, the dynamic-linker cache) and cannot be run this way.
- Images are built with network access; agents and grading run offline.

## Credits and citation

Tasks: CLI-Gym, Lin et al., *CLI-Gym: Scalable CLI Task Generation via Agentic Environment Inversion*,
arXiv:2602.10999 (Apache-2.0), built on SWE-smith repository images. Models: Qwen3.5-9B and Qwen3.5-27B-FP8
(Apache-2.0). Author: Emrul Zawad.

```bibtex
@misc{zawad2026cligymhardened,
  title  = {CLI-Gym under a hardened grader},
  author = {Zawad, Emrul},
  year   = {2026},
  howpublished = {\url{https://huggingface.co/datasets/ehzawad/cligym-hardened-grader}}
}
```
