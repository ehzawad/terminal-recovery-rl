"""Check that a trained LoRA adapter means the same thing to the trainer and to the evaluation server.

Takes recorded token sequences (prompt_ids + completion_ids from rollout traces), scores the completion
tokens with the Hugging Face model + PEFT adapter, then with the vLLM server serving the same adapter
(--lora-modules), and compares per-token log-probabilities. Run with the A6000 otherwise idle: the two
phases run one after the other. A mean absolute difference well under 0.05 nats with a small tail is
the expected result for bf16 on both sides; a large gap means the served adapter is not the trained one.

Usage: python scripts/adapter_parity.py --adapter runs/R_probe/final --traces runs/smoke_v4/P.jsonl [--n 4]
"""

import argparse
import json
import statistics
import urllib.request

import torch

from termrl import server
from termrl.config import MODEL_PATH


def hf_logprobs(adapter: str, seqs: list[tuple[list[int], int]]) -> list[list[float]]:
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText
    base = AutoModelForImageTextToText.from_pretrained(MODEL_PATH, dtype=torch.bfloat16, device_map={"": 0})
    model = PeftModel.from_pretrained(base, adapter).eval()
    out = []
    with torch.no_grad():
        for ids, start in seqs:
            x = torch.tensor([ids], device="cuda")
            logits = model(input_ids=x).logits[0, start - 1:-1].float()
            lp = torch.log_softmax(logits, -1).gather(1, x[0, start:].unsqueeze(1)).squeeze(1)
            out.append(lp.tolist())
    del model, base
    torch.cuda.empty_cache()
    return out


def vllm_logprobs(adapter: str, seqs: list[tuple[list[int], int]]) -> list[list[float]]:
    proc = server.start({"probe": adapter}, log_path="runs/adapter_parity_vllm.log")
    try:
        out = []
        for ids, start in seqs:
            body = json.dumps({"model": "probe", "prompt": ids, "max_tokens": 1, "temperature": 0,
                               "prompt_logprobs": 0}).encode()
            req = urllib.request.Request(f"http://127.0.0.1:{server.PORT}/v1/completions", data=body,
                                         headers={"Content-Type": "application/json"})
            plp = json.load(urllib.request.urlopen(req, timeout=600))["choices"][0]["prompt_logprobs"]
            out.append([next(iter(d.values()))["logprob"] if isinstance(d, dict) and len(d) == 1
                        else d[str(t)]["logprob"] for t, d in zip(ids[start:], plp[start:])])
        return out
    finally:
        server.stop(proc)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--traces", required=True)
    ap.add_argument("--n", type=int, default=4)
    args = ap.parse_args()
    seqs = []
    for line in open(args.traces):
        r = json.loads(line)
        if r.get("completion_ids"):
            seqs.append((r["prompt_ids"] + r["completion_ids"][:1024], len(r["prompt_ids"])))
        if len(seqs) >= args.n:
            break
    a = hf_logprobs(args.adapter, seqs)
    b = vllm_logprobs(args.adapter, seqs)
    diffs = [abs(x - y) for sa, sb in zip(a, b) for x, y in zip(sa, sb)]
    diffs.sort()
    res = {"sequences": len(seqs), "tokens": len(diffs), "mean_abs_diff": statistics.mean(diffs),
           "p99_abs_diff": diffs[int(0.99 * (len(diffs) - 1))], "max_abs_diff": diffs[-1]}
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
