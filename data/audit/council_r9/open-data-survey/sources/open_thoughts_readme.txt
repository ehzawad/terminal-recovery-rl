---
dataset_info:
- config_name: default
  features:
  - name: path
    dtype: string
  - name: task_binary
    dtype: binary
  splits:
  - name: train
    num_bytes: 10346052
    num_examples: 728
  download_size: 10209322
  dataset_size: 10346052
---

<p align="center">
    <img src="https://huggingface.co/datasets/open-thoughts/OpenThoughts1-Agent-SFT/resolve/main/ota-logo.png" width="50%">
</p>

<p align="center">
<a href="https://www.openthoughts.ai/blog/agent" style="margin-right: 24px;">Project</a> |
<a href="https://huggingface.co/datasets/open-thoughts/OpenThoughts-Agent-v1-SFT" style="margin-right: 24px; margin-left: 24px;">SFT dataset</a> |
<a href="https://huggingface.co/datasets/open-thoughts/OpenThoughts-Agent-v1-RL" style="margin-right: 24px; margin-left: 24px;">RL dataset</a> |
<a href="https://huggingface.co/open-thoughts/OpenThinker-Agent-v1-SFT" style="margin-right: 24px; margin-left: 24px;">SFT model</a> |
<a href="https://huggingface.co/open-thoughts/OpenThinker-Agent-v1" style="margin-left: 24px;">RL model</a>
</p>

# OpenThoughts-Agent-v1-RL

A curated RL dataset of ~720 tasks with instructions, environments, and verifiers for agentic training.

## Dataset Description

- **Homepage:** https://www.openthoughts.ai/blog/agent
- **Repository:** https://github.com/open-thoughts/OpenThoughts-Agent

**OpenThoughts-Agent** is an open-source effort to curate the best datasets for training agents. Our first release includes [datasets](https://huggingface.co/collections/open-thoughts/openthinker-agent), [models](https://huggingface.co/collections/open-thoughts/openthinker-agent) and our [research codebase](https://github.com/open-thoughts/OpenThoughts-Agent); 
[OpenThinker-Agent-v1](https://huggingface.co/open-thoughts/OpenThinker-Agent-v1) is a model trained for agentic tasks such as **Terminal-Bench 2.0** and **SWE-Bench**.

We built [OpenThinker-Agent-v1](https://huggingface.co/open-thoughts/OpenThinker-Agent-v1) in two stages: **supervised fine-tuning**, followed by **reinforcement learning**. Each stage required its own data pipeline – RL tasks (instructions, environments, and verifiers) and SFT traces from strong teacher agents completing tasks.

We are excited to release **OpenThoughts-Agent-v1-SFT** and **OpenThoughts-Agent-v1-RL**, our first official OpenThoughts-Agent datasets! 

[OpenThoughts-Agent-v1-SFT](https://huggingface.co/datasets/open-thoughts/OpenThoughts-Agent-v1-SFT) is an SFT trace dataset containing approximately **15,200 traces** drawn from two different data sources we curate:
- **nl2bash**: Simple synthetically generated tasks where the agent has to format shell commands effectively
- **InferredBugs**: A set of bugs in C# and Java collected by Microsoft that we turned into tasks

[OpenThoughts-Agent-v1-RL](https://huggingface.co/datasets/open-thoughts/OpenThoughts-Agent-v1-RL) is an RL dataset containing ~720 tasks drawn from the **nl2bash verified** dataset.

To stabilize training, we built a three-stage filtration pipeline that prunes tasks before they ever hit the learner:

1. Bad verifiers filter: drop tasks with flaky or excessively slow verifiers.
2. Environment stability: remove tasks whose containers take too long to build or tear down.
Optional difficulty filter: discard tasks that even a strong model (GPT-5 Codex) cannot solve in a single pass.

We define a **task** as a triplet of an instruction in the form of a markdown file, an environment defined by a DockerFile, and a verifier in the form of pytests. (The verifier is optional in the SFT setting). All of our environments in this release are generic Ubuntu DockerFiles.

## Interacting with the Data
To explore the tasks locally, you can extract them into a readable format using the following commands (make sure `pyarrow` is installed):

```
curl -L -o extract_parquet_tasks.py \
  "https://huggingface.co/datasets/open-thoughts/OpenThoughts-Agent-v1-RL/raw/main/extract_parquet_tasks.py"

curl -L -o tasks.parquet \
  "https://huggingface.co/datasets/open-thoughts/OpenThoughts-Agent-v1-RL/resolve/main/tasks.parquet"

python extract_parquet_tasks.py tasks.parquet ./extracted_tasks
```

If you prefer a web interface, you can browse the dataset directly in our [interactive trace viewer](https://ot-agent-trace-viewer.replit.app/tasks/open-thoughts%2FOpenThoughts-Agent-v1-RL).

# OpenThinker-Agent-v1 Model Performance

Our [OpenThinker-Agent-v1](https://huggingface.co/open-thoughts/OpenThinker-Agent-v1) model is the state-of-the-art model at its scale on agent benchmarks.

| Model                                                                                           | Harness | Terminal-Bench 2.0 | SWE-Bench Verified | OpenThoughts-TB-Dev |
| ----------------------------------------------------------------------------------------------- | ------- | ------------------ | --------- | ------------------- |
| [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B)                                                | Terminus-2 | 0.0             | 0.7       | 5.7                 |
| **[OpenThinker-Agent-v1](https://huggingface.co/open-thoughts/OpenThinker-Agent-v1)**           | Terminus-2 | 4.9             | 15.7      | 17.3                |
| [Qwen3-32B](https://huggingface.co/Qwen/Qwen3-32B)                                              | Terminus-2 | 1.9             | 5.7       | 10.2                |
| [Qwen/Qwen3-Coder-30B-A3B-Instruct](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct)   | OpenHands  | 10.1           | 49.2      |  24.5                |

# Data Curation and Scaling Recipe

We ablated **15 different approaches**, selecting from both existing sources such as Nemo, SWESmith and Mind2Web, and those we created, such as StackExchange Overflow, Freelancer and Taskmaster.

For each source, we:
1. 🎯 **Generate approximately 10,000 tasks** from the data source
2. 🤖 **Let GPT-5-Nano solve each task once**, resulting in a 10,000 trace SFT dataset
3. 📊 **Evaluate each model on our OpenThoughts-TB-Dev dev set**

## Teacher Model Selection

We ablated was the **choice of teacher**. One would expect that the better the teacher model is on TerminalBench, the better it performs; surprisingly, we find that this is not the case.

Rather, varying teachers in the GPT model family did not improve performance, up to and including the best model on TerminalBench itself, GPT5. However, using **GLM-4.6 as a teacher** led to almost a **2x improvement in downstream score**.


# Links
- 🌐 [OpenThoughts-Agent Project Page](https://www.openthoughts.ai/blog/agent)
- 💻 [OpenThoughts-Agent GitHub Repository](https://github.com/open-thoughts/OpenThoughts-Agent)
- 🧠 [OpenThoughts-Agent-v1-SFT dataset](https://huggingface.co/datasets/open-thoughts/OpenThoughts-Agent-v1-SFT)
- 🧠 [OpenThoughts-Agent-v1-RL dataset](https://huggingface.co/datasets/open-thoughts/OpenThoughts-Agent-v1-RL)
- 🧠 [OpenThoughts-TB-dev dataset](https://huggingface.co/datasets/open-thoughts/OpenThoughts-TB-dev)
- 🤖 [OpenThinker-Agent-v1 model](https://huggingface.co/open-thoughts/OpenThinker-Agent-v1)
- 🤖 [OpenThinker-Agent-v1-SFT model](https://huggingface.co/open-thoughts/OpenThinker-Agent-v1-SFT)

# Citation
```
@misc{openthoughts-agent,
  author = {Team, OpenThoughts-Agent},
  month = Dec,
  title = {{OpenThoughts-Agent}},
  howpublished = {https://www.open-thoughts.ai/blog/agent},
  year = {2025}
}
```