"""Evaluation-time agent loop against an OpenAI-compatible server (vLLM).

The loop is the one the field uses: call the model, run every tool call it made,
append the observations, repeat; the episode ends when a reply carries no tool call
or a budget runs out. Every turn is recorded so failures can be read, not guessed.
"""

from __future__ import annotations

import json
import os
import time
import traceback

from openai import BadRequestError, OpenAI
from transformers import AutoTokenizer
from transformers.utils import get_json_schema

from .env import TerminalEnv

REVISE_NUDGE = (
    "Before finishing, use the terminal to check your result against every requirement in the task "
    "(paths, exact formats, permissions, contents). Fix anything that does not match. When everything "
    "is verified, reply with a brief summary and no tool call."
)

SYSTEM_DEFAULT = (
    "You are an agent operating a Linux terminal through the `bash` tool. Complete the user's task. "
    "When you are finished, reply with a brief summary and no tool call."
)


MODEL_ID = "Qwen/Qwen3.5-9B"
REVISION = "c202236235762e1c871ad0ccb60c8ee5ba337b9a"
# Every component (trainer, colocated vLLM, eval server, tokenizer) reads this one pinned snapshot.
MODEL_PATH = os.path.expanduser(f"~/.cache/huggingface/hub/models--Qwen--Qwen3.5-9B/snapshots/{REVISION}")
_tokenizer = None


def tokenizer():
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    return _tokenizer


def context_tokens(messages: list[dict], enable_thinking: bool) -> int:
    """Length of the rendered conversation, exactly as the chat template (and TRL) would render it."""
    text = tokenizer().apply_chat_template(messages, tools=tool_specs(), add_generation_prompt=True,
                                           enable_thinking=enable_thinking, tokenize=False)
    return len(tokenizer()(text, add_special_tokens=False)["input_ids"])


def tool_specs() -> list[dict]:
    # Same method TRL exposes as a tool during RL, so the schema cannot drift between the two paths.
    return [get_json_schema(TerminalEnv.bash)]


def run_episode(
    client: OpenAI,
    model: str,
    task_root: str,
    *,
    system_prompt: str = SYSTEM_DEFAULT,
    enable_thinking: bool = False,
    max_turns: int = 16,
    max_tokens_per_turn: int = 2048,
    max_context: int = 8192,
    max_completion: int = 6144,
    output_limit: int = 3000,
    temperature: float = 0.7,
    top_p: float = 0.95,
    seed: int | None = None,
    command_timeout: float = 30.0,
    fault_family: str | None = None,
    fault_seed: int = 0,
    check_revise: bool = False,
) -> dict:
    # Budgets mirror the RL rollout limits (TRL max_completion_length / vllm_max_model_length /
    # max_tool_calling_iterations), so every arm is evaluated under the conditions R was trained in.
    env = TerminalEnv(command_timeout=command_timeout, output_limit=output_limit)
    trace: dict = {"task_root": task_root, "model": model, "enable_thinking": enable_thinking, "seed": seed,
                   "system_prompt": system_prompt, "check_revise": check_revise, "turns": [], "end_reason": None}
    t_start = time.monotonic()
    try:
        env.reset(task_root=task_root, fault_family=fault_family, fault_seed=fault_seed)
        trace["fault"] = env._fault.as_dict() if env._fault else None
        messages = [{"role": "system", "content": system_prompt},
                    {"role": "user", "content": env._task.instruction}]
        prompt_len = context_tokens(messages, enable_thinking)
        trace["prompt_tokens"] = prompt_len
        for turn in range(max_turns):
            cur = prompt_len if turn == 0 else context_tokens(messages, enable_thinking)
            budget = min(max_tokens_per_turn, max_completion - (cur - prompt_len), max_context - cur)
            if budget <= 0:
                trace["end_reason"] = "length_budget"
                break
            t0 = time.monotonic()
            try:
                resp = client.chat.completions.create(
                    model=model, messages=messages, tools=tool_specs(), tool_choice="auto",
                    max_tokens=budget, temperature=temperature, top_p=top_p, seed=None if seed is None else seed + turn,
                    extra_body={"chat_template_kwargs": {"enable_thinking": enable_thinking}, "top_k": 20},
                )
            except BadRequestError as e:  # e.g. prompt exceeds the context window
                trace["end_reason"] = "context_overflow" if "context" in str(e).lower() or "length" in str(e).lower() else "api_error"
                trace["api_error"] = str(e)[:500]
                break
            choice = resp.choices[0]
            msg = choice.message
            reasoning = getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None) or ""
            calls = msg.tool_calls or []
            rec = {"turn": turn, "latency": round(time.monotonic() - t0, 3), "finish_reason": choice.finish_reason,
                   "prompt_tokens": resp.usage.prompt_tokens, "completion_tokens": resp.usage.completion_tokens,
                   "reasoning_chars": len(reasoning), "content": msg.content, "tool_calls": []}
            assistant = {"role": "assistant", "content": msg.content or ""}
            if calls:
                assistant["tool_calls"] = [{"id": c.id, "type": "function",
                                            "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                           for c in calls]
            messages.append(assistant)
            if not calls:
                rec["reasoning"] = reasoning[-4000:]
                trace["turns"].append(rec)
                if check_revise and not trace.get("revise_used") and choice.finish_reason != "length":
                    # Verifier-free inference-compute control: one self-check round inside the same budget.
                    trace["revise_used"] = turn
                    messages.append({"role": "user", "content": REVISE_NUDGE})
                    continue
                trace["end_reason"] = "truncated" if choice.finish_reason == "length" else "stopped"
                break
            for c in calls:
                try:
                    args = json.loads(c.function.arguments or "{}")
                    out = env.bash(**args) if c.function.name == "bash" else f"[error: unknown tool {c.function.name}]"
                except Exception as e:  # malformed arguments are the model's failure, reported back to it
                    out = f"[error: could not run tool call: {e}]"
                    args = {"_raw": c.function.arguments}
                rec["tool_calls"].append({"arguments": args, "observation": out})
                messages.append({"role": "tool", "tool_call_id": c.id, "content": out})
            trace["turns"].append(rec)
        else:
            trace["end_reason"] = "max_turns"
        verdict = env._finish()
        trace["verdict"] = {"passed": verdict.passed, "total": verdict.total, "success": verdict.success,
                            "reward": verdict.reward, "failures": verdict.failures, "error": verdict.error}
        trace["commands"] = env._log
        trace["fault_observed_call"] = env._fault_observed_call
        trace["fault_cleared"] = env._fault_cleared
    except Exception:
        trace["end_reason"] = trace["end_reason"] or "harness_error"
        trace["harness_error"] = traceback.format_exc()[-3000:]
        env._teardown()
    trace["seconds"] = round(time.monotonic() - t_start, 2)
    trace["generated_tokens"] = sum(t["completion_tokens"] for t in trace["turns"])
    return trace
