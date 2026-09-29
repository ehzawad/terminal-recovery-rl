import hashlib, json, re, sys, collections, zipfile, pyarrow.parquet as pq
from pathlib import Path
P = Path("/mnt/sdb/arafat/ehz/llm/.pools/audit9")
def h(ds, tid): return hashlib.sha256(f"audit-a9|{ds}|{tid}".encode()).hexdigest()
out = {}
# SETA
names = [n for s, n in json.load(open(sys.argv[1])) if n != ".DS_Store"]
subset = {n: s for s, n in json.load(open(sys.argv[1]))}
roots = collections.defaultdict(list)
for n in names: roots[re.sub(r"__[bd]\d+$", "", n)].append(n)
quota = {"ask_ubuntu": 8, "stack_overflow": 6, "kaggle_notebook": 4, "unix_linux_se": 4, "nl2bash": 2}
seta = []
for src, q in quota.items():
    rs = sorted((r for r in roots if r.startswith(src + "__")), key=lambda r: h("SETA", r))[:q]
    for r in rs:
        v = min(roots[r], key=lambda n: h("SETA", n))
        seta.append({"root": r, "task": v, "subset": subset[v]})
out["SETA"] = seta
# TMax
t = pq.read_table(P / "TMax-15K/data/train-00000-of-00001.parquet")
cols = t.column_names
idc = "task_id" if "task_id" in cols else cols[0]
ids = t.column(idc).to_pylist()
out["TMax"] = [{"task": i} for i in sorted(ids, key=lambda i: h("TMax", i))[:16]]
# LiteCoder
lt = sorted(d.name for d in (P / "LiteCoder-Terminal-RL-preview").iterdir() if d.is_dir() and (d / "task.toml").exists())
out["LiteCoder"] = [{"task": i} for i in sorted(lt, key=lambda i: h("LiteCoder", i))[:8]]
out["meta"] = {"salt": "audit-a9", "tmax_id_col": idc, "n_tmax": len(ids), "n_lite": len(lt), "n_seta_roots": len(roots)}
json.dump(out, open("results/A9/sample.json", "w"), indent=1)
print(out["meta"]); [print(k, [x["task"] for x in v]) for k, v in out.items() if k != "meta"]
