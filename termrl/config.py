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


def budget_line(max_commands: int) -> str:
    """The fixed harness line that ends the user message when a command budget is set (A7)."""
    return (f"(Terminal budget: at most {max_commands} bash tool calls for this task. Every call counts, including "
            "calls that fail or time out; calls beyond the budget are not run. The task is graded as it stands "
            "when you stop or when the budget is used up.)")


def user_content(instruction: str, max_commands: int | None) -> str:
    """The user message: the task instruction, plus the budget line when a budget is set."""
    return f"{instruction}\n\n{budget_line(max_commands)}" if max_commands else instruction


# Episode limits shared by evaluation (termrl/rollout.py), SFT collection and RL (scripts/train_grpo.py).
MAX_TOOL_TURNS = 16        # TRL max_tool_calling_iterations
MAX_COMPLETION = 6144      # TRL max_completion_length (tool-result tokens count toward it)
MAX_MODEL_LEN = 8192       # TRL vllm_max_model_length / evaluation server --max-model-len
COMMAND_TIMEOUT = 30.0     # seconds per bash call
OUTPUT_LIMIT = 3000        # characters of tool output shown to the model (head + tail)
