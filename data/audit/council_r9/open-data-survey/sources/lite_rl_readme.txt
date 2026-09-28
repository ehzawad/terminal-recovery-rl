---
license: mit
task_categories:
- text-generation
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train.parquet
tags:
- terminal
- rl
- code
---

# LiteCoder-Terminal-RL-preview

[**Paper**](https://huggingface.co/papers/2605.29559) | [**Code**](https://github.com/icip-cas/LiteCoder) | [**Blog Post**](https://huggingface.co/blog/Lite-Coder/releasing-litecoder-terminal)

This dataset contains **602 standardized Harbor terminal environments** and was released as part of the paper [LiteCoder-Terminal: Scaling Long-Horizon Terminal Environments for Learning Language Agents](https://huggingface.co/papers/2605.29559). 

Unlike static text-only instructions, these environments are fully executable and are designed to support the training of terminal-based agents.

## Environment Generation Pipeline

The lack of high-quality, executable training environments is currently a major challenge for training terminal agents. Raw task descriptions lack the execution feedback required for techniques like rejection sampling and reinforcement learning, so an executable environment is essential. We implemented a five-stage synthesis pipeline to convert sampled tasks into the Harbor format using the Claude Agent SDK:

1. **Task refinement**: rewrite raw task descriptions into clear and testable instructions
2. **Environment setup**: prepare the execution environment and required resources
3. **Reference solution generation**: produce a working solution for the task
4. **Verifier creation**: construct test cases and evaluation logic
5. **Harbor packaging**: assemble everything into the standard Harbor format

![pipeline_flowchart.drawio-2](https://cdn-uploads.huggingface.co/production/uploads/6942a253b5344869abe7abfc/wq_w7MMpljBU8LJbT3aYV.png)

## Environment Structure

Each environment represents a standardized terminal task instance organized in the Harbor format, which is as the following:

```bash
├── instruction.md
├── task.toml
├── environment
│   ├── Dockerfile
│   └── ...
├── solution
│   ├── solve.sh
│   └── ...
└── tests
    ├── test.sh
    └── ...
```

## Citation

```bibtex
@article{peng2026litecoderterminal,
  title={LiteCoder-Terminal: Scaling Long-Horizon Terminal Environments for Learning Language Agents},
  author={Peng, Xiaoxuan and Zhang, Kaiqi and Lu, Xinyu and Cao, Boxi and Lu, Yaojie and Lin, Hongyu and Han, Xianpei and Sun, Le},
  journal={arXiv preprint arXiv:2605.29559},
  year={2026}
}
```