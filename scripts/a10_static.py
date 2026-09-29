"""A10 static screen: model-free flags per sampled task plus corpus-wide counts. Flags, not verdicts."""
import json, re, sys
from collections import Counter
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import a9_static as S9  # noqa: E402

POOL = Path("/mnt/sdb/arafat/ehz/llm/.pools/audit10")
OUT = ROOT / "results/A10"
TRACE = re.compile(r"hint|recovery|\.bak\b|\.orig\b|backup|\.key\b|passphrase|password|/root/\.[a-z_]+|bash_history|cipher|base64|openssl enc|xor", re.I)
KERNEL = re.compile(r"uname -r|linux-headers|insmod|modprobe|seccomp|/proc/sys|sysctl|iptables|LD_PRELOAD|ld\.so\.preload|ldconfig", re.I)
REPO_EDIT = re.compile(r"/testbed/(?!\.git)")


def flags(df: str) -> dict:
    run = "\n".join(l for l in df.splitlines() if not l.startswith("FROM"))
    return {"trace_terms": sorted(set(m.group(0).lower() for m in TRACE.finditer(run))),
            "kernel_or_loader": sorted(set(m.group(0) for m in KERNEL.finditer(run))),
            "edits_repo_source": bool(REPO_EDIT.search(run)), "removes_git": "rm -rf /testbed/.git" in run,
            "build_network": sorted(set(m.group(0) for m in S9.NET.finditer(run))),
            "danger": sorted(set(m.group(0)[:40] for m in S9.DANGER.finditer(run))),
            "run_lines": sum(1 for l in df.splitlines() if l.startswith("RUN"))}


d = pd.read_parquet(POOL / "train.parquet")
sample = json.load(open(OUT / "sample.json"))["tasks"]
by = d.set_index("task_id")
per = {t["key"]: flags(by.loc[t["task_id"]].dockerfile) for t in sample}
allf = [flags(x) for x in d.dockerfile]
corpus = {"tasks": len(d), "with_trace_terms": sum(bool(f["trace_terms"]) for f in allf),
          "kernel_or_loader": sum(bool(f["kernel_or_loader"]) for f in allf), "uname_r": int(d.dockerfile.str.contains("uname -r").sum()),
          "edits_repo_source": sum(f["edits_repo_source"] for f in allf), "removes_git": sum(f["removes_git"] for f in allf),
          "hard": int(d.task_id.str.endswith(".hard").sum())}
json.dump({"per_task": per, "corpus": corpus}, open(OUT / "static_screen.json", "w"), indent=1)
print(json.dumps(corpus))
for k, v in per.items():
    print(k[8:70].ljust(62), "trace:", v["trace_terms"][:4], "kern:", v["kernel_or_loader"][:3], "repo:", v["edits_repo_source"], "git-:", v["removes_git"])
