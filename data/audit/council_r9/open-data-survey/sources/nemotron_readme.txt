---
license: cc-by-4.0
task_categories:
- question-answering
language:
- en
tags:
- code
size_categories:
- 100K<n<1M
configs:
- config_name: dataset_adapters
  data_files:
  - split: train
    path: "dataset_adapters/*.parquet"

- config_name: skill_based_easy
  data_files:
  - split: train
    path: "synthetic_tasks/skill_based/easy/*/data_filtered.parquet"

- config_name: skill_based_medium
  data_files:
  - split: train
    path: "synthetic_tasks/skill_based/medium/*/data_filtered.parquet"

- config_name: skill_based_mixed
  data_files:
  - split: train
    path: "synthetic_tasks/skill_based/mixed/*/data_filtered.parquet"
---

# Terminal-Corpus: Large-Scale SFT Dataset for Terminal Agents

Terminal-Corpus is a large-scale Supervised Fine-Tuning (SFT) dataset designed to scale the terminal interaction capabilities of Large Language Models (LLMs). Developed by NVIDIA, this dataset was built using the **Terminal-Task-Gen** pipeline, which combines dataset adaptation with synthetic task generation across diverse domains.

## 🚀 Key Results & Performance

The high-quality trajectories in Terminal-Corpus enable models of various sizes to achieve performance that rivals or exceeds much larger frontier models on the **Terminal-Bench 2.0** benchmark.

### 1. Overall Performance Comparison
Training on Terminal-Corpus yields substantial gains across the Qwen3 model family:

| Model Size | Base Model (Qwen3) Accuracy | Nemotron-Terminal Accuracy | Improvement |
| :--- | :---: | :---: | :---: |
| **8B** | 2.5% ± 0.5 | **13.0% ± 2.2** | ~5.2x |
| **14B** | 4.0% ± 1.3 | **20.2% ± 2.7** | ~5.0x |
| **32B** | 3.4% ± 1.6 | **27.4% ± 2.4** | ~8.0x |

The **Nemotron-Terminal-32B** (27.4%) outperforms the 480B-parameter **Qwen3-Coder** (23.9%) and **Gemini 2.5 Flash** (16.9%). **Nemotron-Terminal-14B** (20.2%) achieves higher accuracy than the 120B **GPT-OSS (high)** (18.7%).

### 2. Domain-Specific Breakthroughs
The dataset unlocks functional utility in complex domains where base models previously showed near-zero capability:

| Category | Qwen3-32B (Base) | Nemotron-Terminal-32B |
| :--- | :---: | :---: |
| **Data Querying** | 0.0% | **60.0%** |
| **Model Training** | 0.0% | **50.0%** |
| **Data Processing** | 5.0% | **50.0%** |
| **Debugging** | 0.0% | **33.3%** |
| **Software Engineering** | 5.0% | **31.7%** |

## 📂 Dataset Composition

The released dataset contains approximately 366k high-quality execution trajectories split into two major streams:

* **Dataset Adapters (~226k samples)**: Transformations of high-quality Math, Code, and Software Engineering (SWE) datasets into terminal-based formats.
* **Skill-based Synthetic Tasks (~140k samples)**: Novel tasks generated from a structured taxonomy of primitive terminal skills.

## 📜 Citation
If you use this dataset in your research, please cite the following work:
```bibtex
@misc{pi2026dataengineeringscalingllm,
      title={On Data Engineering for Scaling LLM Terminal Capabilities}, 
      author={Renjie Pi and Grace Lam and Mohammad Shoeybi and Pooya Jannaty and Bryan Catanzaro and Wei Ping},
      year={2026},
      eprint={2602.21193},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2602.21193}, 
}
