"""Start and stop the evaluation vLLM server on the pinned A6000 (one card, one job at a time)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request

from .config import MODEL_PATH

A6000 = "GPU-4754ca84-fd1d-907b-5c18-7c578d001bda"
PORT = 8765
VLLM = os.path.join(os.path.dirname(sys.executable), "vllm")


def start(lora: dict[str, str] | None = None, log_path: str = "runs/vllm_server.log") -> subprocess.Popen:
    """Serve the base model as 'q9' plus any LoRA adapters under their given names."""
    env = dict(os.environ, CUDA_DEVICE_ORDER="PCI_BUS_ID", CUDA_VISIBLE_DEVICES=A6000, HF_HUB_OFFLINE="1")
    cmd = [VLLM, "serve", MODEL_PATH, "--host", "127.0.0.1", "--port", str(PORT), "--served-model-name", "q9",
           "--max-model-len", "8192", "--gpu-memory-utilization", "0.80", "--max-num-seqs", "32",
           "--limit-mm-per-prompt", '{"image":0,"video":0}', "--enable-prefix-caching",
           "--enable-lora", "--max-lora-rank", "16", "--max-loras", "2"]
    if lora:
        cmd += ["--lora-modules", *[f"{k}={v}" for k, v in lora.items()]]
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    proc = subprocess.Popen(cmd, stdout=open(log_path, "a"), stderr=subprocess.STDOUT, env=env)
    deadline = time.time() + 1200
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"vLLM exited with {proc.returncode}; see {log_path}")
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/v1/models", timeout=2)
            return proc
        except Exception:
            time.sleep(5)
    proc.kill()
    raise RuntimeError("vLLM did not become ready within 20 minutes")


def stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=120)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=60)
