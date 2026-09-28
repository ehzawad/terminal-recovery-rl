"""Arm R: outcome RL (GRPO-family) with a LoRA adapter, straight from the instruct checkpoint.

Rollouts run in the same TerminalEnv as evaluation (TRL turns `TerminalEnv.bash` into the tool),
vLLM is colocated on the one card and sleeps during the update, there is no reference model
(beta=0), and the loss follows Dr. GRPO: rewards are centred within each group but not divided by
the group's standard deviation, and token losses are normalised by a constant.

Registered limits (A2, A5): at most 64 updates of 4 groups x 4 completions (1,024 trajectories) and
18 GPU-hours, both counted across restarts (run_state.json); liveness stop rules as in LivenessGate.
TRL's vLLM importance-sampling correction is pinned explicitly (sequence_mask, cap 3.0) and its
masked share is logged by TRL.

Usage:
  python scripts/train_grpo.py --rows data/rows/train_configs.jsonl --out runs/R_seed1 \
      --system-prompt-file prompts/pX.txt [--resume] [--smoke]
"""

import argparse
import hashlib
import json
import math
import os
import threading
import time

import torch
from datasets import Dataset
from peft import LoraConfig
from transformers import TrainerCallback
from trl import GRPOConfig, GRPOTrainer

from termrl.config import COMMAND_TIMEOUT, MAX_COMPLETION, MAX_MODEL_LEN, MAX_TOOL_TURNS, OUTPUT_LIMIT, user_content
from termrl.config import MODEL_PATH as MODEL  # pinned local snapshot of Qwen/Qwen3.5-9B
from termrl.env import TerminalEnv

# Language-model projections only. in_proj_qkv and in_proj_z are packed together by vLLM, so they are
# targeted together; in_proj_a/in_proj_b (also a packed pair) and the vision tower are left alone.
LORA_TARGETS = (r"model\.language_model\.layers\.\d+\.(self_attn\.(q|k|v|o)_proj|mlp\.(gate|up|down)_proj"
                r"|linear_attn\.(in_proj_qkv|in_proj_z|out_proj))")


class RecordingGRPOTrainer(GRPOTrainer):
    """Writes every rollout exactly as generated (token ids, tool mask, verdict) for arm D and auditing."""

    def __init__(self, *a, rollout_log: str, **k):
        super().__init__(*a, **k)
        self._rollout_log = rollout_log
        self._batch_counter = 0

    def _generate_and_score_completions(self, inputs):
        out = super()._generate_and_score_completions(inputs)
        pad = self._tokenizer.pad_token_id
        with open(self._rollout_log, "a") as f:
            for i, env in enumerate(self.environments):
                p = out["prompt_ids"][i][out["prompt_mask"][i].bool()].tolist()
                c = out["completion_ids"][i]
                n = len(c)
                while n > 0 and int(c[n - 1]) == pad:  # completions are right-padded
                    n -= 1
                # TRL zeroes the completion mask (and with it the usable tool mask) of truncated rollouts;
                # they carry no loss in R and are excluded from D.
                truncated = n > 0 and int(out["completion_mask"][i].sum()) == 0
                v = env._verdict
                f.write(json.dumps({
                    "attempt_id": f"{self.state.global_step}:{self._batch_counter}:{i}", "truncated": truncated,
                    "reward": env.get_reward() if v is not None or env._broken else None,
                    "harness_error": env._broken or env._infra_error,
                    "step": self.state.global_step, "task_root": env._task.root if env._task else None,
                    "fault": env._fault.as_dict() if env._fault else None,
                    "fault_observed_call": env._fault_observed_call, "fault_cleared": env._fault_cleared,
                    "collateral": env._collateral, "fabricated_input": env._fabricated_input,
                    "verdict": None if v is None else {"passed": v.passed, "total": v.total, "success": v.success,
                                                       "reward": v.reward, "error": v.error},
                    "prompt_ids": p, "completion_ids": c[:n].tolist(), "tool_mask": out["tool_mask"][i][:n].tolist(),
                }) + "\n")
        self._batch_counter += 1
        return out


class LivenessGate(TrainerCallback):
    """Registered stop rules (gate 4, windows fixed in A5), with hours and trajectories kept across restarts.

    - non-finite loss or gradient norm;
    - 3 consecutive updates whose groups all have zero reward variance;
    - two consecutive windows of 32 updates (128 groups) with < 60% informative groups;
    - two consecutive windows of 8 updates (128 trajectories) with > 5% truncated completions
      (TRL's completions/clipped_ratio = completions that hit the length limit);
    - 18 GPU-hours or 1,024 trajectories in total.
    """

    def __init__(self, state_path: str, max_hours: float, max_trajectories: int, per_step: int):
        self.state_path, self.max_hours, self.max_traj, self.per_step = state_path, max_hours, max_trajectories, per_step
        self.state = json.load(open(state_path)) if os.path.exists(state_path) else {"hours": 0.0, "trajectories": 0}
        self.t0 = time.time()
        self.no_signal_streak = 0
        self.informative, self.clipped = [], []
        self.reason = None

    def _save(self):
        s = dict(self.state, hours=self.state["hours"] + (time.time() - self.t0) / 3600)
        json.dump(s, open(self.state_path, "w"))
        return s

    def on_log(self, args, state, control, logs=None, **kw):
        if not logs or "loss" not in logs:
            return
        self.state["trajectories"] += self.per_step
        s = self._save()
        if any(isinstance(logs.get(k), float) and not math.isfinite(logs[k]) for k in ("loss", "grad_norm")):
            self.reason = "non-finite loss or gradient"
        zero = logs.get("frac_reward_zero_std", 0.0)
        self.no_signal_streak = self.no_signal_streak + 1 if zero >= 1.0 else 0
        if self.no_signal_streak >= 3:
            self.reason = "3 consecutive updates with no within-group reward variance"
        self.informative.append(1.0 - zero)
        self.clipped.append(logs.get("completions/clipped_ratio", 0.0))
        inf, clp = self.informative, self.clipped
        if len(inf) >= 64 and len(inf) % 32 == 0 and sum(inf[-64:-32]) / 32 < 0.60 and sum(inf[-32:]) / 32 < 0.60:
            self.reason = "<60% informative groups in two consecutive windows of 128 groups"
        if len(clp) >= 16 and len(clp) % 8 == 0 and sum(clp[-16:-8]) / 8 > 0.05 and sum(clp[-8:]) / 8 > 0.05:
            self.reason = ">5% truncated completions in two consecutive windows of 128 trajectories"
        if s["hours"] > self.max_hours:
            self.reason = f"GPU-hour cap of {self.max_hours} h reached"
        if s["trajectories"] >= self.max_traj:
            self.reason = f"trajectory cap of {self.max_traj} reached"
        if self.reason:
            print(f"LIVENESS GATE: stopping: {self.reason}", flush=True)
            control.should_training_stop = True


def load_rows(path: str, system_prompt: str) -> tuple[Dataset, int | None]:
    """Training rows as TRL prompts; every row must carry the same command budget (A7), which is returned."""
    rows, budgets = [], set()
    for line in open(path):
        r = json.loads(line)
        mc = r.get("max_commands")
        budgets.add(mc)
        instruction = open(os.path.join(r["task_root"], "instruction.md")).read().strip()
        rows.append({
            "prompt": [{"role": "system", "content": system_prompt},
                       {"role": "user", "content": user_content(instruction, mc)}],
            "task_root": r["task_root"], "fault_family": r.get("fault_family") or "", "fault_seed": int(r.get("fault_seed", 0)),
            "max_commands": int(mc or 0),
        })
    if len(budgets) != 1:
        raise SystemExit(f"rows mix command budgets: {sorted(budgets, key=str)}")
    return Dataset.from_list(rows), budgets.pop()


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
    ap.add_argument("--system-prompt-file", required=True)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--max-trajectories", type=int, default=1024)
    ap.add_argument("--max-steps", type=int, default=64)  # A2: at most 64 updates x 16 trajectories
    ap.add_argument("--max-hours", type=float, default=18.0)  # A2: R's GPU-hour cap
    ap.add_argument("--num-generations", type=int, default=4)
    ap.add_argument("--groups-per-step", type=int, default=4)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--vllm-util", type=float, default=0.45)  # 0.40 leaves no KV room beside the policy weights
    ap.add_argument("--max-completion", type=int, default=MAX_COMPLETION)
    ap.add_argument("--max-model-len", type=int, default=MAX_MODEL_LEN)
    ap.add_argument("--max-tool-turns", type=int, default=MAX_TOOL_TURNS)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    system_prompt = open(args.system_prompt_file).read().strip()
    ds, max_commands = load_rows(args.rows, system_prompt)
    if max_commands:  # the tool-round limit equals the command budget, exactly as in evaluation
        args.max_tool_turns = max_commands
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
        vllm_importance_sampling_correction=True,
        vllm_importance_sampling_mode="sequence_mask",
        vllm_importance_sampling_clip_max=3.0,
        use_vllm=True,
        vllm_mode="colocate",
        vllm_enable_sleep_mode=True,
        vllm_gpu_memory_utilization=args.vllm_util,
        vllm_max_model_length=args.max_model_len,
        gradient_checkpointing=True,
        bf16=True,
        model_init_kwargs={"dtype": "bfloat16"},
        logging_steps=1,
        save_steps=32,  # two scheduled checkpoint candidates (steps 32 and 64) for dev_monitor selection
        save_only_model=False,  # optimizer state kept so an interrupted run can resume
        report_to="none",
        log_completions=False,
    )
    lora = LoraConfig(r=args.lora_r, lora_alpha=2 * args.lora_r, lora_dropout=0.0, target_modules=LORA_TARGETS,
                      task_type="CAUSAL_LM")
    os.makedirs(args.out, exist_ok=True)
    gate = LivenessGate(os.path.join(args.out, "run_state.json"), args.max_hours, args.max_trajectories,
                        completions_per_step)
    trainer = RecordingGRPOTrainer(model=MODEL, args=cfg, train_dataset=ds, peft_config=lora,
                                   environment_factory=lambda: TerminalEnv(command_timeout=COMMAND_TIMEOUT,
                                                                           output_limit=OUTPUT_LIMIT),
                                   callbacks=[gate], rollout_log=os.path.join(args.out, "rollouts.jsonl"))
    probe = MemoryProbe()
    probe.start()
    t0 = time.time()
    trainer.train(resume_from_checkpoint=True if args.resume else None)
    probe.stop()
    summary = {"seconds": round(time.time() - t0, 1), "peak_device_gib": round(probe.peak_gib, 2),
               "liveness_stop": gate.reason, "run_state": gate._save(),
               "system_prompt_file": args.system_prompt_file, "max_commands": max_commands,
               "max_tool_turns": args.max_tool_turns,
               "system_prompt_sha": hashlib.sha256(system_prompt.encode()).hexdigest()[:16],
               "torch_max_allocated_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2),
               "log_history": trainer.state.log_history}
    with open(os.path.join(args.out, "run_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps({k: v for k, v in summary.items() if k != "log_history"}))
    trainer.save_model(os.path.join(args.out, "final"))


if __name__ == "__main__":
    main()
