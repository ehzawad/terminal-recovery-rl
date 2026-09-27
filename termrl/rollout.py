"""Token-level multi-turn episodes, built exactly the way TRL's GRPOTrainer builds a rollout.

The prompt is rendered by the processor with TRL's (prefix-preserving, if needed) template and the
`bash` tool; every model turn is generated from raw token ids; tool calls are parsed with TRL's
`parse_response`; tool results are appended as the suffix tokens TRL cuts from a dummy
conversation. Evaluation, rejection sampling (SFT data) and RL therefore all see byte-identical
sequences. A record keeps `prompt_ids`, `completion_ids` and `tool_mask` (1 = model token), which
is also the SFT training format.
"""

from __future__ import annotations

import json
import time
import traceback

from openai import OpenAI
from transformers import AutoProcessor
from trl.chat_template_utils import (
    add_response_schema,
    get_training_chat_template,
    is_chat_template_prefix_preserving,
    parse_response,
)
from trl.data_utils import prepare_multimodal_messages

from .config import REVISE_NUDGE
from .env import TerminalEnv


class Renderer:
    """Mirror of GRPOTrainer's processing-class setup (grpo_trainer.py: response schema, template, suffixes)."""

    def __init__(self, model_path: str, enable_thinking: bool = False):
        pc = AutoProcessor.from_pretrained(model_path)
        tok = pc.tokenizer
        if getattr(tok, "response_template", None) is None and getattr(tok, "response_schema", None) is None:
            pc = add_response_schema(pc)
        self.pc = pc
        self.tok = pc.tokenizer
        self.kwargs = {"enable_thinking": enable_thinking}
        self.chat_template = None if is_chat_template_prefix_preserving(pc) else get_training_chat_template(pc)
        self.tools = [TerminalEnv().bash]  # bound method: the schema TRL renders from the environment

    def prompt_ids(self, messages: list[dict]) -> list[int]:
        out = self.pc.apply_chat_template(conversation=[prepare_multimodal_messages(messages)], tools=self.tools,
                                          chat_template=self.chat_template, add_generation_prompt=True,
                                          tokenize=True, return_dict=True, **self.kwargs)
        return list(out["input_ids"][0])

    def tool_suffix_ids(self, tool_messages: list[dict]) -> list[int]:
        dummy = [{"role": "user", "content": "dummy"},
                 {"role": "assistant", "content": "",
                  "tool_calls": [{"type": "function", "function": {"name": tool_messages[0]["name"], "arguments": {}}}]}]
        dummy = prepare_multimodal_messages(dummy)
        tms = prepare_multimodal_messages(tool_messages)
        prefix = self.pc.apply_chat_template(dummy, add_generation_prompt=False, tokenize=True,
                                             chat_template=self.chat_template, return_dict=False, **self.kwargs)[0]
        full = self.pc.apply_chat_template(dummy + tms, add_generation_prompt=True, tokenize=True,
                                           chat_template=self.chat_template, return_dict=False, **self.kwargs)[0]
        eos = [i for i, t in enumerate(prefix) if t == self.tok.eos_token_id]
        if eos:
            prefix = prefix[: eos[-1] + 1]
        if list(full[: len(prefix)]) != list(prefix):
            raise ValueError("tool suffix: EOS-trimmed prefix is not a prefix of the full rendering")
        return list(full[len(prefix):])

    def parse(self, ids: list[int], prefix: list[int]) -> dict:
        return parse_response(self.tok, ids, prefix=prefix) if ids else {}


def run_episode(
    client: OpenAI,
    renderer: Renderer,
    model: str,
    task_root: str,
    *,
    system_prompt: str,
    fault_family: str | None = None,
    fault_seed: int = 0,
    max_tool_turns: int = 16,
    max_completion: int = 6144,
    max_model_len: int = 8192,
    temperature: float = 0.7,
    top_p: float = 0.95,
    top_k: int = 20,
    seed: int | None = None,
    command_timeout: float = 30.0,
    output_limit: int = 3000,
    check_revise: bool = False,
    revise_nudge: str | None = None,
) -> dict:
    env = TerminalEnv(command_timeout=command_timeout, output_limit=output_limit)
    trace: dict = {"task_root": task_root, "model": model, "system_prompt": system_prompt, "seed": seed,
                   "check_revise": check_revise, "turns": [], "end_reason": None}
    t_start = time.monotonic()
    try:
        env.reset(task_root=task_root, fault_family=fault_family, fault_seed=fault_seed)
        trace["fault"] = env._fault.as_dict() if env._fault else None
        messages = [{"role": "system", "content": system_prompt},
                    {"role": "user", "content": env._task.instruction}]
        prompt_ids = renderer.prompt_ids(messages)
        completion_ids: list[int] = []
        tool_mask: list[int] = []
        tool_rounds = 0
        while True:
            budget = min(max_completion - len(completion_ids), max_model_len - len(prompt_ids) - len(completion_ids))
            if budget <= 0:
                trace["end_reason"] = "length_budget"
                break
            t0 = time.monotonic()
            resp = client.completions.create(
                model=model, prompt=prompt_ids + completion_ids, max_tokens=budget, temperature=temperature,
                top_p=top_p, seed=None if seed is None else seed + len(trace["turns"]),
                extra_body={"top_k": top_k, "return_token_ids": True, "skip_special_tokens": False},
            )
            ch = resp.choices[0]
            new_ids = list(ch.token_ids)
            parsed = renderer.parse(new_ids, prompt_ids + completion_ids)
            completion_ids += new_ids
            tool_mask += [1] * len(new_ids)
            calls = parsed.get("tool_calls") or []
            rec = {"turn": len(trace["turns"]), "latency": round(time.monotonic() - t0, 3), "finish_reason": ch.finish_reason,
                   "new_tokens": len(new_ids), "content": parsed.get("content"), "tool_calls": []}
            trace["turns"].append(rec)
            if ch.finish_reason == "length":
                trace["end_reason"] = "truncated"
                break
            if not calls:
                if check_revise and "revise_used" not in trace:
                    # Verifier-free inference-compute control: one self-check round inside the same budget.
                    trace["revise_used"] = rec["turn"]
                    user_ids = _user_suffix_ids(renderer, revise_nudge or REVISE_NUDGE)
                    completion_ids += user_ids
                    tool_mask += [0] * len(user_ids)
                    continue
                trace["end_reason"] = "stopped"
                break
            if tool_rounds >= max_tool_turns:
                trace["end_reason"] = "max_tool_turns"
                break
            tool_messages = []
            for c in calls:
                fn = c.get("function", {})
                name, args = fn.get("name"), fn.get("arguments") or {}
                try:
                    if isinstance(args, str):
                        args = json.loads(args)
                    out = env.bash(**args) if name == "bash" else {"error": f"Tool {name} not found."}
                except Exception as e:  # same shape TRL reports for a failing tool call
                    out = {"error": str(e)}
                rec["tool_calls"].append({"arguments": args, "observation": str(out)})
                tool_messages.append({"role": "tool", "name": name, "content": str(out)})
            suffix = renderer.tool_suffix_ids(tool_messages)
            if len(completion_ids) + len(suffix) > max_completion or \
                    len(prompt_ids) + len(completion_ids) + len(suffix) >= max_model_len:
                trace["end_reason"] = "length_budget"  # TRL drops the tool result and ends the rollout here
                break
            completion_ids += suffix
            tool_mask += [0] * len(suffix)
            tool_rounds += 1
        verdict = env._finish()
        trace["verdict"] = {"passed": verdict.passed, "total": verdict.total, "success": verdict.success,
                            "reward": verdict.reward, "failures": verdict.failures, "error": verdict.error}
        trace["commands"] = env._log
        trace["fault_observed_call"] = env._fault_observed_call
        trace["fault_cleared"] = env._fault_cleared
        trace["collateral"] = env._collateral
        trace["damaged_paths"] = sorted(env._damaged)
        trace["fabricated_input"] = env._fabricated_input
        trace["fixtures"] = [p for p, _ in env._fixtures]
        trace["reward"] = -1.0 if env._collateral is not None else 0.5 * float(verdict.success) + 0.5 * verdict.reward
        trace["safe_success"] = bool(verdict.success) and env._collateral is None
        trace["prompt_ids"] = prompt_ids
        trace["completion_ids"] = completion_ids
        trace["tool_mask"] = tool_mask
    except Exception:
        trace["end_reason"] = trace["end_reason"] or "harness_error"
        trace["harness_error"] = traceback.format_exc()[-3000:]
        env._teardown()
    trace["seconds"] = round(time.monotonic() - t_start, 2)
    trace["generated_tokens"] = sum(t["new_tokens"] for t in trace["turns"])
    return trace


def _user_suffix_ids(renderer: Renderer, text: str) -> list[int]:
    """Tokens appended after the model's final <|im_end|> to open a new user turn and assistant header.

    Qwen's template re-renders earlier assistant turns once a user turn follows (it drops their
    thinking block), so this transition is not prefix-preserving; the suffix is therefore built from
    a lone user message, which renders as `<|im_start|>user ... <|im_start|>assistant` + header.
    """
    alone = renderer.pc.apply_chat_template(prepare_multimodal_messages([{"role": "user", "content": text}]),
                                            add_generation_prompt=True, tokenize=True,
                                            chat_template=renderer.chat_template, return_dict=False,
                                            **renderer.kwargs)[0]
    if not renderer.tok.decode(alone).startswith("<|im_start|>user"):
        raise ValueError("unexpected rendering of a lone user turn")
    return renderer.tok("\n", add_special_tokens=False)["input_ids"] + list(alone)
