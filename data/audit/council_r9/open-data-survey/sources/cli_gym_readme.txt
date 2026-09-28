---
pretty_name: CLI-Gym Verified Problem Instances
language:
- en
license: apache-2.0
tags:
- cli
- agentic-coding
- docker
- terminal-bench
size_categories:
- 1K<n<10K
papers:
- 2602.10999
---

# CLI-Gym Verified Problem Instances

This is the official dataset release of **environment-intensive (CLI) problem instances** from **CLI-Gym**.

Each instance is designed to evaluate and train an agent’s ability to **diagnose and repair real runtime environments** via CLI interaction (dependencies, permissions, system configuration, networking, etc.), with **executable verification** through unit tests.

---

## News

- **[2026-02-28] Full dataset release! (1,655 CLI-Gym problem instances**).
- [2026-02-14] Initial dataset release (1,321 verified problem instances).

---

## Overview

- [Introduction](#introduction)
- [Main statistics](#main-statistics)
- [Data schema](#data-schema)
- [Usage](#usage)
- [Safety / security notes](#safety--security-notes)
- [Citation](#citation)
- [License](#license)

---

## Introduction

⭐ **What’s special about this dataset**

- **Environment-intensive**: tasks require real CLI interaction and system-level debugging beyond code-only edits.
- **Reproducible**: each instance includes a Dockerfile/docker-compose environment spec and a test script.

---

## Main statistics

- **Total instances**: **1,321**
- **Split(s)**: `train`

### CLI-Gym vs Terminal-Bench (from the paper)

| Category | Metric | Terminal-Bench | CLI-Gym |
|---|---|---:|---:|
| Size | # Instances | 229 | 1655 |
|  | # Images | 22 | 29 |
| Issue Text | Length (words) | 140.7 | 159.1 |
| Dockerfile | # Lines | 5.8 | 6.8 |
| Tests | # Fail-to-pass | 7.9 | 20.4 |
|  | # Pass-to-pass | 0.0 | 29.6 |
| **Cost** |  | **93 Contributors** | **2.3B Tokens** |

## Data schema

This release is stored as:

- `train.parquet`

Each row corresponds to one problem instance with the following columns:

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | string | Unique identifier (folder name / slug) |
| `instruction` | string | Issue-style problem statement given to the agent |
| `dockerfile` | string | Dockerfile content to build the task environment |
| `docker_compose` | string | docker-compose YAML content |
| `run_tests` | string | Verification script content (bash script) |

---

## Usage

### Load from the Hub

```python
from datasets import load_dataset

ds = load_dataset("LiberCoders/CLI-Gym")  # replace with your Hub path if different
train = ds["train"]
print(train[0]["task_id"])
print(train[0]["instruction"][:300])
```

### Load locally (from Parquet)

```python
from datasets import load_dataset

ds = load_dataset(
    "parquet",
    data_files={"train": "train.parquet"},
)
train = ds["train"]
```

## Safety / security notes

These tasks are intended to be executed **inside isolated containers**.

- Do **NOT** run any Dockerfile or test script on your host system.
- Do **NOT** mount sensitive host directories into containers.
- Treat all task content as **untrusted** (it may execute arbitrary shell commands when used by an agent runtime).

---

## Citation

If you use this dataset, please cite the CLI-Gym paper:

```bibtex
@article{lin2026cligym,
  title   = {CLI-Gym: Scalable CLI Task Generation via Agentic Environment Inversion},
  author  = {Lin, Yusong and Wang, Haiyang and Wu, Shuzhe and Fan, Lue and Pan, Feiyang and Zhao, Sanyuan and Tu, Dandan},
  year    = {2026},
  journal = {arXiv preprint arXiv:2602.10999}
}
```

---

## License

apache-2.0