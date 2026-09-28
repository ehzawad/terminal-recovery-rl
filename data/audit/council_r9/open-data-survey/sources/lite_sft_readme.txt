---
license: mit
task_categories:
- text-generation
language:
- en
tags:
- terminal
- agent
- sft
- synthetic-data
---

# LiteCoder-SFT-Terminal

[**Paper**](https://huggingface.co/papers/2605.29559) | [**Code**](https://github.com/icip-cas/LiteCoder) | [**Blog Post**](https://huggingface.co/blog/Lite-Coder/releasing-litecoder-terminal)

**LiteCoder-SFT-Terminal** is a dataset of 11,255 agent trajectories in terminal environments, introduced in the paper [LiteCoder-Terminal: Scaling Long-Horizon Terminal Environments for Learning Language Agents](https://huggingface.co/papers/2605.29559). 

Fine-tuned on this data, the [LiteCoder-Terminal-30b-a3b-sft](https://huggingface.co/Lite-Coder/LiteCoder-Terminal-30b-a3b-sft) model achieves 31.5% Pass@1 on Terminal Bench Pro, while the [LiteCoder-Terminal-4b-sft](https://huggingface.co/Lite-Coder/LiteCoder-Terminal-4b-sft) model shows distinct gains over its baseline.

## **Released Artifacts**

| Date | Type | Link |
| --- | --- | --- |
| 2026/04/13 | Model | [**LiteCoder-Terminal-30b-a3b-sft**](https://huggingface.co/Lite-Coder/LiteCoder-Terminal-30b-a3b-sft) |
| 2026/04/13 | Model | [**LiteCoder-Terminal-4b-sft**](https://huggingface.co/Lite-Coder/LiteCoder-Terminal-4b-sft) |
| 2026/04/13 | Dataset | [**LiteCoder-Terminal-SFT**](https://huggingface.co/datasets/Lite-Coder/LiteCoder-Terminal-SFT) |
| 2026/04/13 | Dataset | [**LiteCoder-Terminal-World-Model-SFT**](https://huggingface.co/datasets/Lite-Coder/LiteCoder-Terminal-World-Model-SFT) |
| 2026/04/13 | Dataset | [**LiteCoder-Terminal-RL-preview**](https://huggingface.co/datasets/Lite-Coder/LiteCoder-Terminal-RL-preview) |
| 2026/04/13 | Code | [**icip-cas/LiteCoder**](https://github.com/icip-cas/LiteCoder) |

## What’s New

- **Taxonomy expansion:** Introducing new task categories to cover a broader range of terminal interactions.
- **Data scale expansion:** Scaling from a sub-1k setup to **11,255** **total trajectories**.
- **Scaffold expansion:** Moving from **Terminus-only** training to a **multi-scaffold** setting including OpenHands and Claude Code.
- **Improved results:** Higher performance on **Terminal** **Bench** **1.0** **/** **2.0 / Pro**.

## Taxonomy Expansion

We expanded the task taxonomy to cover a broader range of real-world terminal interactions, introducing 3 new categories: **coding**, **scientific/numerical computing,** and **games**. This ensures the model is exposed to highly diverse scenarios, ranging from rigorous developer workflows to the dynamic, state-driven environments typically found in terminal games.

## Scaffolding Extension

Given the vast array of agent scaffolds, a robust model must be able to adapt to diverse setups. To improve cross-scaffold generalization, we expanded our trajectory collection beyond the initial Terminus-only setup. The updated training pipeline now integrates trajectories from popular frameworks like Claude Code and OpenHands.

## Dataset Statistics

The LiteCoder-SFT dataset comprises **11,255** trajectories spanning **10** task categories, with an average of **27.4** turns per trajectory. The dataset also incorporates trajectories from three distinct agent scaffolds: **Terminus‑2** (86.6%), **OpenHands** (7.1%), and **Claude Code** (6.3%).

![combined_crest_p2_4](https://cdn-uploads.huggingface.co/production/uploads/6942a253b5344869abe7abfc/a6oG9TEIOQo4aSeMAw9yu.png)

## Results

To ensure the reliability of our evaluation, the reported Pass@1 scores represent the average performance across four independent runs in Terminal Bench 1.0 and 2.0.

### Terminal Bench 1.0 Performance

| Model | Agent | pass@1 | pass@4 |
| --- | --- | --- | --- |
| **LiteCoder-Terminal-30b-a3b-sft** | Terminus 2 | **24.38%** | **40%** |
| Qwen3-30B-A3B-Nex-N1 | Openhands | 18.44% | 32.5% |
| LiteCoder-30a3b-Terminal-preview | Terminus 2 | 16.56% | 27.5% |
| Qwen3-30B-A3B-Instruct | Terminus 2 | 16.56% | 28.75% |
| **LiteCoder-Terminal-4b-sft** | Terminus 2 | **14.69%** | **28.75%** |
| OpenThinker-Agent-v1 | Terminus 2 | 11.25% | 25% |
| LiteCoder-4b-Terminal-preview | Terminus 2 | 9.38% | 20% |
| Qwen3-4B-Instruct | Terminus 2 | 6.25% | 15% |

### Terminal Bench 2.0 Performance

| Model | Agent | pass@1 | pass@4 |
| --- | --- | --- | --- |
| **LiteCoder-Terminal-30b-a3b-sft** | Terminus 2 | **12.36%** | **23.60%** |
| Qwen3-30B-A3B-Nex-N1 | Openhands | 12.36% | 23.60% |
| LiteCoder-30a3b-Terminal-preview | Terminus 2 | 6.18% | 13.75% |
| Qwen3-30B-A3B-Instruct | Terminus 2 | 5.34% | 11.24% |
| **LiteCoder-Terminal-4b-sft** | Terminus 2 | **4.78%** | **10.11%** |
| OpenThinker-Agent-v1 | Terminus 2 | 4.49% | 10.1% |
| LiteCoder-4b-Terminal-preview | Terminus 2 | 4.78% | 12.36% |
| Qwen3-4B-Instruct | Terminus 2 | 1.12% | 3.37% |

### Terminal Bench Pro Performance

| Model | Agent | pass@1 |
| --- | --- | --- |
| **LiteCoder-Terminal-30b-a3b-sft** | Terminus 2 | **31.5%** |
| LiteCoder-30a3b-Terminal-preview | Terminus 2 | 22.0% |
| **LiteCoder-Terminal-4b-sft** | Terminus 2 | **21.5%** |
| Qwen3-30B-A3B-Nex-N1 | Openhands | 21.0% |
| Qwen3-30B-A3B-Instruct | Terminus 2 | 20.5% |
| OpenThinker-Agent-v1 | Terminus 2 | 19.5% |
| LiteCoder-4b-Terminal-preview | Terminus 2 | 15.0% |
| Qwen3-4B-Instruct | Terminus 2 | 3.5% |

## Citation

```bibtex
@article{peng2026litecoderterminal,
  title={LiteCoder-Terminal: Scaling Long-Horizon Terminal Environments for Learning Language Agents},
  author={Peng, Xiaoxuan and Zhang, Kaiqi and Lu, Xinyu and Cao, Boxi and Lu, Yaojie and Lin, Hongyu and Han, Xianpei and Sun, Le},
  journal={arXiv preprint arXiv:2605.29559},
  year={2026}
}
```