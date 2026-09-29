"""A10 seeded draw: 24 CLI-Gym tasks, one per base image, in sha256 order."""
import hashlib, json, re
from pathlib import Path
import pandas as pd

POOL = Path("/mnt/sdb/arafat/ehz/llm/.pools/audit10")
OUT = Path(__file__).resolve().parents[1] / "results/A10"

d = pd.read_parquet(POOL / "train.parquet")
d["h"] = [hashlib.sha256(f"audit-a10|CLI-Gym|{t}".encode()).hexdigest() for t in d.task_id]
d["base"] = [re.search(r"^FROM\s+(\S+)", x, re.M).group(1) for x in d.dockerfile]
rows, seen = [], set()
for _, r in d.sort_values("h").iterrows():
    if r.base in seen:
        continue
    seen.add(r.base)
    rows.append({"key": f"CLIGym__{r.task_id}", "task_id": r.task_id, "base": r.base, "hash": r.h, "canary": len(rows) < 2})
    if len(rows) == 24:
        break
OUT.mkdir(parents=True, exist_ok=True)
json.dump({"revision": "552945c5aaf07d9715549a798c98ee13bb5b7f06", "tasks": rows}, open(OUT / "sample.json", "w"), indent=1)
for r in rows:
    print(r["canary"] and "C" or " ", r["task_id"], r["base"].split(".")[-2])
