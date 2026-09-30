"""A12 train draw: first 200 of the pool in sha256("a12-train|id") order, then grouped by base image."""
import hashlib, json, re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
d = pd.read_parquet("/mnt/sdb/arafat/ehz/llm/.pools/audit10/train.parquet")
a10 = {t["task_id"] for t in json.load(open(ROOT / "results/A10/sample.json"))["tasks"]}
a11 = {k[8:] for k in json.load(open(ROOT / "results/A11/tasks.json"))}
pool = d[~d.task_id.isin(a10 | a11) & ~d.dockerfile.str.contains("uname -r")].copy()
pool["h"] = [hashlib.sha256(f"a12-train|{t}".encode()).hexdigest() for t in pool.task_id]
pool["base"] = [re.search(r"^FROM\s+(\S+)", x, re.M).group(1) for x in pool.dockerfile]
take = pool.sort_values("h").head(200).sort_values(["base", "h"])
rows = [{"key": f"CLIGym__{r.task_id}", "task_id": r.task_id, "base": r.base, "hash": r.h} for r in take.itertuples()]
json.dump({"pool": len(pool), "tasks": rows}, open(ROOT / "results/A12/train_tasks.json", "w"), indent=1)
print(len(pool), "in pool;", len(rows), "drawn over", take.base.nunique(), "images")
