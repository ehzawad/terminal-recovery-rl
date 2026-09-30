"""A11 headroom draw: sha256 order over CLI-Gym minus A10's sample and `uname -r` tasks, max 2 per base image.
Writes the full ordered candidate list; the runner takes the first 48 that build and pass gold, in order."""
import hashlib, json, re
from pathlib import Path
import pandas as pd

POOL = Path("/mnt/sdb/arafat/ehz/llm/.pools/audit10")
OUT = Path(__file__).resolve().parents[1] / "results/A11"
d = pd.read_parquet(POOL / "train.parquet")
a10 = {t["task_id"] for t in json.load(open(OUT.parent / "A10/sample.json"))["tasks"]}
d = d[~d.task_id.isin(a10) & ~d.dockerfile.str.contains("uname -r")].copy()
d["h"] = [hashlib.sha256(f"headroom-a11|{t}".encode()).hexdigest() for t in d.task_id]
d["base"] = [re.search(r"^FROM\s+(\S+)", x, re.M).group(1) for x in d.dockerfile]
order, per, taken = [], {}, set()
for cap in (2, 3, 4):
    for _, r in d.sort_values("h").iterrows():
        if r.task_id in taken or per.get(r.base, 0) >= cap:
            continue
        per[r.base] = per.get(r.base, 0) + 1
        taken.add(r.task_id)
        order.append({"key": f"CLIGym__{r.task_id}", "task_id": r.task_id, "base": r.base, "hash": r.h, "cap_tier": cap})
OUT.mkdir(parents=True, exist_ok=True)
json.dump({"revision": "552945c5aaf07d9715549a798c98ee13bb5b7f06", "n_candidates": len(d), "ordered": order},
          open(OUT / "candidates.json", "w"), indent=1)
print(len(d), "candidates;", len(order), "in capped order (need 48)")
