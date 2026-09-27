"""Pinned model and the fixed texts shared by every arm."""

import os

MODEL_ID = "Qwen/Qwen3.5-9B"
REVISION = "c202236235762e1c871ad0ccb60c8ee5ba337b9a"
# Trainer, colocated vLLM, evaluation server and tokenizer all read this one pinned snapshot.
MODEL_PATH = os.path.expanduser(f"~/.cache/huggingface/hub/models--Qwen--Qwen3.5-9B/snapshots/{REVISION}")

SYSTEM_DEFAULT = (
    "You are an agent operating a Linux terminal through the `bash` tool. Complete the user's task. "
    "When you are finished, reply with a brief summary and no tool call."
)

REVISE_NUDGE = (
    "Before finishing, use the terminal to check your result against every requirement in the task "
    "(paths, exact formats, permissions, contents). Fix anything that does not match. When everything "
    "is verified, reply with a brief summary and no tool call."
)
