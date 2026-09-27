"""Check that a trained LoRA adapter means the same thing to the trainer and to the evaluation server.

Takes recorded token sequences (prompt_ids + completion_ids from rollout traces), scores the completion
tokens with the Hugging Face model + PEFT adapter, then with the vLLM server serving the same adapter
(--lora-modules), and compares per-token log-probabilities on the model's own tokens (tool_mask 1; tool
output is excluded). The same comparison with the adapter disabled on both sides gives the floor that
kernel numerics alone produce, and adapter-vs-base on each side shows the adapter actually moves the model
(an untrained adapter, lora_B = 0, moves nothing and proves nothing). Run with the A6000 otherwise idle: the
two phases run one after the other. The adapter gap should sit at that floor; a gap well above it means the
served adapter is not the trained one.

Usage: python scripts/adapter_parity.py --adapter runs/R_probe/final --traces runs/smoke_v4/P.jsonl [--n 4]
"""

import argparse
import json
import statistics
import urllib.request

import torch

from termrl import server
from termrl.config import MODEL_PATH


def hf_logprobs(adapter: str, seqs: list[tuple[list[int], int]]) -> dict[str, list[list[float]]]:
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText
    base = AutoModelForImageTextToText.from_pretrained(MODEL_PATH, dtype=torch.bfloat16, device_map={"": 0})
    model = PeftModel.from_pretrained(base, adapter).eval()

    def score():
        out = []
        for ids, start in seqs:
            x = torch.tensor([ids], device="cuda")
            logits = model(input_ids=x).logits[0, start - 1:-1].float()
            lp = torch.log_softmax(logits, -1).gather(1, x[0, start:].unsqueeze(1)).squeeze(1)
            out.append(lp.tolist())
        return out

    with torch.no_grad():
        res = {"probe": score()}
        with model.disable_adapter():
            res["q9"] = score()
    del model, base
    torch.cuda.empty_cache()
    return res


def vllm_logprobs(adapter: str, seqs: list[tuple[list[int], int]]) -> dict[str, list[list[float]]]:
    proc = server.start({"probe": adapter}, log_path="runs/adapter_parity_vllm.log")
    try:
        res = {}
        for name in ("probe", "q9"):
            out = []
            for ids, start in seqs:
                body = json.dumps({"model": name, "prompt": ids, "max_tokens": 1, "temperature": 0,
                                   "prompt_logprobs": 0}).encode()
                req = urllib.request.Request(f"http://127.0.0.1:{server.PORT}/v1/completions", data=body,
                                             headers={"Content-Type": "application/json"})
                plp = json.load(urllib.request.urlopen(req, timeout=600))["choices"][0]["prompt_logprobs"]
                out.append([d[str(t)]["logprob"] for t, d in zip(ids[start:], plp[start:])])
            res[name] = out
        return res
    finally:
        server.stop(proc)


def compare(a: list[list[float]], b: list[list[float]], masks: list[list[int]]) -> dict:
    diffs, seq_sums = [], []
    for sa, sb, m in zip(a, b, masks):
        d = [x - y for x, y, k in zip(sa, sb, m) if k]
        diffs += [abs(x) for x in d]
        seq_sums.append(round(sum(d), 3))
    diffs.sort()
    return {"tokens": len(diffs), "mean_abs_diff": round(statistics.mean(diffs), 4),
            "p99_abs_diff": round(diffs[int(0.99 * (len(diffs) - 1))], 4), "max_abs_diff": round(diffs[-1], 4),
            "sequence_log_ratio": seq_sums}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--traces", required=True)
    ap.add_argument("--n", type=int, default=4)
    args = ap.parse_args()
    seqs, masks = [], []
    for line in open(args.traces):
        r = json.loads(line)
        if r.get("completion_ids"):
            seqs.append((r["prompt_ids"] + r["completion_ids"][:1024], len(r["prompt_ids"])))
            masks.append(r["tool_mask"][:1024])
        if len(seqs) >= args.n:
            break
    a = hf_logprobs(args.adapter, seqs)
    b = vllm_logprobs(args.adapter, seqs)
    res = {"sequences": len(seqs), "adapter": compare(a["probe"], b["probe"], masks),
           "adapter_effect_hf": compare(a["probe"], a["q9"], masks),
           "adapter_effect_vllm": compare(b["probe"], b["q9"], masks),
           "base_floor": compare(a["q9"], b["q9"], masks),
           "adapter_all_tokens": compare(a["probe"], b["probe"], [[1] * len(m) for m in masks])}
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
