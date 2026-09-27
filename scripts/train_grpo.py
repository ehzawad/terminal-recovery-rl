"""Arm R: outcome RL (GRPO-family) with a LoRA adapter, straight from the instruct checkpoint.

Rollouts run in the same TerminalEnv as evaluation (TRL turns `TerminalEnv.bash` into the tool),
vLLM is colocated on the one card and sleeps during the update, there is no reference model
(beta=0), and the loss follows Dr. GRPO: rewards are centred within each group but not divided by
the group's standard deviation, and token losses are normalised by a constant.

Usage:
  python scripts/train_grpo.py --rows data/rl_rows_train.jsonl --out runs/grpo_seed1 [--smoke]
"""

import argparse
import json
import os
import threading
import time

import torch
from datasets import Dataset
from peft import LoraConfig
from trl import GRPOConfig, GRPOTrainer

from termrl.config import MODEL_PATH as MODEL  # pinned local snapshot of Qwen/Qwen3.5-9B
from termrl.config import SYSTEM_DEFAULT
from termrl.env import TerminalEnv
# Language-model projections only. in_proj_qkv and in_proj_z are packed together by vLLM, so they are
# targeted together; in_proj_a/in_proj_b (also a packed pair) and the vision tower are left alone.
LORA_TARGETS = (r"model\.language_model\.layers\.\d+\.(self_attn\.(q|k|v|o)_proj|mlp\.(gate|up|down)_proj"
                r"|linear_attn\.(in_proj_qkv|in_proj_z|out_proj))")


class RolloutEnv(TerminalEnv):
    """Reward = 0.5 * complete success + 0.5 * fraction of hidden checks passed (fixed before training)."""

    def get_reward(self) -> float:
        v = self._finish()
        if v.error:  # infrastructure failure: excluded from the update, never scored as a policy outcome
            return None
        return 0.5 * float(v.success) + 0.5 * v.reward


def load_rows(path: str, system_prompt: str) -> Dataset:
    rows = []
    for line in open(path):
        r = json.loads(line)
        rows.append({
            "prompt": [{"role": "system", "content": system_prompt},
                       {"role": "user", "content": open(os.path.join(r["task_root"], "instruction.md")).read().strip()}],
            "task_root": r["task_root"], "fault_family": r.get("fault_family") or "", "fault_seed": int(r.get("fault_seed", 0)),
        })
    return Dataset.from_list(rows)


class MemoryProbe(threading.Thread):
    """Samples device memory in use (all processes' view via NVML-free torch API) every second."""

    def __init__(self):
        super().__init__(daemon=True)
        self.peak_gib = 0.0
        self._stop = threading.Event()

    def run(self):
        while not self._stop.is_set():
            free, total = torch.cuda.mem_get_info()
            self.peak_gib = max(self.peak_gib, (total - free) / 2**30)
            time.sleep(1.0)

    def stop(self):
        self._stop.set()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--system-prompt-file")
    ap.add_argument("--max-steps", type=int, default=32)
    ap.add_argument("--num-generations", type=int, default=4)
    ap.add_argument("--groups-per-step", type=int, default=4)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--vllm-util", type=float, default=0.45)
    ap.add_argument("--max-completion", type=int, default=6144)
    ap.add_argument("--max-model-len", type=int, default=8192)
    ap.add_argument("--max-tool-turns", type=int, default=16)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    system_prompt = open(args.system_prompt_file).read().strip() if args.system_prompt_file else SYSTEM_DEFAULT
    ds = load_rows(args.rows, system_prompt)
    completions_per_step = args.num_generations * args.groups_per_step
    cfg = GRPOConfig(
        output_dir=args.out,
        seed=args.seed,
        max_steps=1 if args.smoke else args.max_steps,
        learning_rate=args.lr,
        lr_scheduler_type="constant_with_warmup",
        warmup_steps=0 if args.smoke else 2,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=completions_per_step,
        num_generations=args.num_generations,
        max_completion_length=args.max_completion,
        max_tool_calling_iterations=args.max_tool_turns,
        chat_template_kwargs={"enable_thinking": False},
        temperature=1.0,
        beta=0.0,
        loss_type="dr_grpo",
        scale_rewards="none",
        mask_truncated_completions=True,
        use_vllm=True,
        vllm_mode="colocate",
        vllm_enable_sleep_mode=True,
        vllm_gpu_memory_utilization=args.vllm_util,
        vllm_max_model_length=args.max_model_len,
        gradient_checkpointing=True,
        bf16=True,
        model_init_kwargs={"dtype": "bfloat16"},
        logging_steps=1,
        save_steps=8,
        save_only_model=True,
        report_to="none",
        log_completions=False,
    )
    lora = LoraConfig(r=args.lora_r, lora_alpha=2 * args.lora_r, lora_dropout=0.0, target_modules=LORA_TARGETS,
                      task_type="CAUSAL_LM")
    trainer = GRPOTrainer(model=MODEL, args=cfg, train_dataset=ds, peft_config=lora,
                          environment_factory=lambda: RolloutEnv(command_timeout=30.0, output_limit=3000))
    probe = MemoryProbe()
    probe.start()
    t0 = time.time()
    trainer.train()
    probe.stop()
    summary = {"seconds": round(time.time() - t0, 1), "peak_device_gib": round(probe.peak_gib, 2),
               "torch_max_allocated_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2),
               "log_history": trainer.state.log_history}
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "run_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps({k: v for k, v in summary.items() if k != "log_history"}))
    trainer.save_model(os.path.join(args.out, "final"))


if __name__ == "__main__":
    main()
