---
license: apache-2.0
language:
- en
task_categories:
- reinforcement-learning
tags:
- terminal
- agent
- bash
- code
- synthetic
- environment
- task-benchmark
pretty_name: SETA-Env
size_categories:
- 1K<n<10K
---

# SETA-Env

![SETA](assets/TerminalAgent.jpg)

[![GitHub](https://img.shields.io/badge/GitHub-camel--ai%2Fseta-black?logo=github)](https://github.com/camel-ai/seta) [![🤗 Model](https://img.shields.io/badge/🤗%20Model-Qwen3--8B--SETA--Env--RL-blue)](https://huggingface.co/camel-ai/Qwen3-8B-SETA-Env-RL)

SETA-Env is an open-source verifiable RL terminal environment dataset for community training and evaluation.

This release contains two top-level subsets:

- `SETA_Synth`: synthesized tasks
- `SETA_Evolve`: evolved variants of terminal-agent tasks

The current release contains `4567` environments:

- `SETA_Synth`: `3255`
- `SETA_Evolve`: `1312`

## What Is Included

Each task is packaged as a self-contained Harbor-style task directory with the files needed to run the task, build its environment, execute a reference solution, and run tests.

## Dataset Structure

```text
SETA_Synth/
├── ask_ubuntu__...
├── kaggle_notebook__...
├── nl2bash__...
├── stack_overflow__...
└── unix_linux_se__...

SETA_Evolve/
├── ask_ubuntu__...__b1
├── ask_ubuntu__...__d1
├── kaggle_notebook__...__b1
├── nl2bash__...__b1
├── stack_overflow__...__d1
└── unix_linux_se__...__b1
```

A typical released task folder looks like:

```text
{task_id}/
├── task.toml
├── instruction.md
├── environment/
│   ├── Dockerfile
│   └── ...
├── solution/
│   └── solve.sh
└── tests/
    ├── test.sh
    └── test_outputs.py
```

## Source Breakdown

### SETA_Synth

| Source | Count |
|---|---:|
| `ask_ubuntu` | 1013 |
| `kaggle_notebook` | 637 |
| `nl2bash` | 276 |
| `stack_overflow` | 884 |
| `unix_linux_se` | 445 |
| **Total** | **3255** |

### SETA_Evolve

| Source | Count |
|---|---:|
| `ask_ubuntu` | 783 |
| `kaggle_notebook` | 147 |
| `nl2bash` | 9 |
| `stack_overflow` | 256 |
| `unix_linux_se` | 117 |
| **Total** | **1312** |

## Notes

- Task folder names are the primary identifiers in this release.
- `SETA_Evolve` task names include suffixes such as `__b1` and `__d1` to distinguish evolved variants.
- `__b1` means context change round 1.
- `__d1` means difficulty change round 1.

## Suggested Usage

```python
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="camel-ai/seta-env-release",
    repo_type="dataset",
    local_dir="./seta_release",
)
```

To download only one subset:

```python
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="camel-ai/seta-env-release",
    repo_type="dataset",
    allow_patterns="SETA_Synth/**",
    local_dir="./seta_release",
)
```
