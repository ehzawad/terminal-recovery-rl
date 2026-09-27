"""Arms S and D: LoRA SFT on verified successful trajectories (token records from termrl.rollout).

Each record already holds `prompt_ids`, `completion_ids` and `tool_mask` exactly as the policy
produced them, so the training sequence is the rollout sequence byte for byte. Loss falls only on
the model's own tokens (tool_mask == 1); prompt and tool-result tokens are context. The loop is
hand-written so the gradient-accumulation normalisation is explicit: every update divides by the
number of supervised tokens in its whole accumulation group.

Usage:
  python scripts/train_sft.py --data runs/S/round1_success.jsonl [--data more.jsonl] --out runs/S/r1 \
      --epochs 2 --save-epochs 1 2
"""

import argparse
import json
import math
import os
import random
import time

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForImageTextToText

from termrl.config import MODEL_PATH

LORA_TARGETS = (r"model\.language_model\.layers\.\d+\.(self_attn\.(q|k|v|o)_proj|mlp\.(gate|up|down)_proj"
                r"|linear_attn\.(in_proj_qkv|in_proj_z|out_proj))")


def load_examples(paths: list[str], max_len: int) -> list[tuple[list[int], list[int]]]:
    out, skipped = [], 0
    for path in paths:
        for line in open(path):
            r = json.loads(line)
            # Safe successes only (A2): complete success and no collateral modification.
            if not (r.get("verdict") or {}).get("success") or r.get("collateral") is not None \
                    or r.get("harness_error") or "completion_ids" not in r:
                continue
            ids = r["prompt_ids"] + r["completion_ids"]
            mask = [0] * len(r["prompt_ids"]) + r["tool_mask"]
            if len(ids) > max_len:
                skipped += 1
                continue
            out.append((ids, mask))
    print(f"{len(out)} training sequences ({skipped} over {max_len} tokens skipped)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", action="append", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--save-epochs", type=int, nargs="*", default=[1, 2])
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--seqs-per-update", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=8192)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-hours", type=float, default=3.0)
    args = ap.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    examples = load_examples(args.data, args.max_len)
    model = AutoModelForImageTextToText.from_pretrained(MODEL_PATH, dtype=torch.bfloat16, device_map={"": 0})
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(r=args.lora_r, lora_alpha=2 * args.lora_r, lora_dropout=0.0,
                                             target_modules=LORA_TARGETS, task_type="CAUSAL_LM"))
    model.print_trainable_parameters()
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=0.0, betas=(0.9, 0.999))
    updates_per_epoch = math.ceil(len(examples) / args.seqs_per_update)
    total_updates = updates_per_epoch * args.epochs
    warmup = max(1, total_updates // 20)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, (s + 1) / warmup) * 0.5 * (1 + math.cos(math.pi * min(1.0, s / total_updates))))
    os.makedirs(args.out, exist_ok=True)
    log = open(os.path.join(args.out, "train_log.jsonl"), "a")
    t0, step = time.time(), 0
    model.train()
    for epoch in range(1, args.epochs + 1):
        order = list(range(len(examples)))
        random.shuffle(order)
        for u in range(updates_per_epoch):
            group = [examples[i] for i in order[u * args.seqs_per_update:(u + 1) * args.seqs_per_update]]
            n_tok = sum(sum(m[1:]) for _, m in group)  # supervised next-token targets in the whole group
            loss_sum = 0.0
            for ids, mask in group:
                # Logits only where the next token is the model's own (a full 8K x 248K-vocab fp32 logit
                # tensor would be ~8 GB); position i predicts token i+1.
                pos = [i for i in range(len(ids) - 1) if mask[i + 1]]
                x = torch.tensor([ids], device="cuda")
                logits = model(input_ids=x, logits_to_keep=torch.tensor(pos, device="cuda")).logits[0]
                targets = torch.tensor([ids[i + 1] for i in pos], device="cuda")
                tok_loss = sum(torch.nn.functional.cross_entropy(logits[c:c + 1024].float(), targets[c:c + 1024],
                                                                 reduction="sum")
                               for c in range(0, len(pos), 1024))
                (tok_loss / n_tok).backward()
                loss_sum += tok_loss.item()
                del logits, tok_loss
            gnorm = torch.nn.utils.clip_grad_norm_(params, 1.0).item()
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            rec = {"epoch": epoch, "step": step, "loss": loss_sum / n_tok, "grad_norm": gnorm,
                   "lr": sched.get_last_lr()[0], "tokens": n_tok, "hours": (time.time() - t0) / 3600,
                   "peak_gib": torch.cuda.max_memory_allocated() / 2**30}
            log.write(json.dumps(rec) + "\n")
            log.flush()
            print(rec, flush=True)
            if rec["hours"] > args.max_hours:
                print("time allowance reached")
                break
        if epoch in args.save_epochs or rec["hours"] > args.max_hours:
            model.save_pretrained(os.path.join(args.out, f"epoch{epoch}"))
        if rec["hours"] > args.max_hours:
            break


if __name__ == "__main__":
    main()
