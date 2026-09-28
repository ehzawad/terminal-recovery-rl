"""Systems probe: long-context serving on the A6000 with synthetic prompts (no task data, no scoring).

Starts vLLM at --max-model-len 32768, then for each concurrency level sends that many requests at once, each
a distinct synthetic ~24K-token prompt (random words, so the prefix cache cannot help) asking for 1,024 new
tokens, and records wall time, prefill and decode throughput and the peak GPU memory in use.

Usage: python scripts/probe_longctx.py > results/probe_longctx.json
"""

import concurrent.futures as cf
import json
import random
import subprocess
import threading
import time
import urllib.request

from termrl import server

WORDS = ("alpha beta gamma delta file line value count report error warning info user host path size date "
         "time table column row index key token parse merge sort filter join split").split()


def gpu_peak(stop: threading.Event, out: list) -> None:
    while not stop.is_set():
        r = subprocess.run(["nvidia-smi", "--query-gpu=uuid,memory.used", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True)
        for line in r.stdout.splitlines():
            uuid, used = [x.strip() for x in line.split(",")]
            if uuid == server.A6000:
                out.append(int(used))
        time.sleep(1)


def request(prompt: str, max_tokens: int) -> dict:
    body = json.dumps({"model": "q9", "prompt": prompt, "max_tokens": max_tokens, "temperature": 0.7,
                       "ignore_eos": True}).encode()
    t0 = time.time()
    req = urllib.request.Request(f"http://127.0.0.1:{server.PORT}/v1/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=3600))
    return {"seconds": time.time() - t0, "prompt_tokens": r["usage"]["prompt_tokens"],
            "completion_tokens": r["usage"]["completion_tokens"]}


def main() -> None:
    proc = server.start(log_path="runs/vllm_probe_longctx.log", max_model_len=32768, max_num_seqs=8)
    res = {"max_model_len": 32768, "gpu_memory_utilization": 0.80, "levels": {}}
    try:
        rng = random.Random(0)
        for n in (1, 6, 8):
            prompts = [" ".join(rng.choice(WORDS) for _ in range(20000)) for _ in range(n)]
            peak, stop = [], threading.Event()
            th = threading.Thread(target=gpu_peak, args=(stop, peak), daemon=True)
            th.start()
            t0 = time.time()
            with cf.ThreadPoolExecutor(n) as ex:
                outs = list(ex.map(lambda p: request(p, 1024), prompts))
            wall = time.time() - t0
            stop.set()
            th.join()
            pt = sum(o["prompt_tokens"] for o in outs)
            ct = sum(o["completion_tokens"] for o in outs)
            res["levels"][n] = {"wall_seconds": round(wall, 1), "prompt_tokens_each": outs[0]["prompt_tokens"],
                                "completion_tokens_total": ct, "tokens_per_second_total": round((pt + ct) / wall, 1),
                                "decode_tokens_per_second": round(ct / wall, 1),
                                "peak_gpu_mib": max(peak) if peak else None}
            print(json.dumps({n: res["levels"][n]}), flush=True)
    finally:
        server.stop(proc)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
