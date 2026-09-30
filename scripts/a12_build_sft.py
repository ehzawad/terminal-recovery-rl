"""A12 SFT data: teacher train episodes that pass grader v2 (max 2 per task), as token records for train_sft.py."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "results/A12/teacher_train"
out, stats = [], {"tasks_usable": 0, "tasks_with_pass": 0, "episodes": 0, "v2_pass": 0, "kept": 0}
for f in sorted(D.glob("*.json")):
    r = json.loads(f.read_text())
    if not r.get("usable"):
        continue
    stats["tasks_usable"] += 1
    passed = [e for e in r["episodes"] if e.get("v2")]
    stats["episodes"] += len(r["episodes"])
    stats["v2_pass"] += len(passed)
    stats["tasks_with_pass"] += bool(passed)
    for e in passed[:2]:
        tr = json.loads((D / "traces" / r["key"] / f"{e['i']}.json").read_text())
        if tr.get("end_reason") in ("truncated", "length_budget", "harness_error") or "completion_ids" not in tr:
            continue
        out.append({"key": r["key"], "i": e["i"], "prompt_ids": tr["prompt_ids"], "completion_ids": tr["completion_ids"],
                    "tool_mask": tr["tool_mask"], "verdict": {"success": True}, "collateral": None, "end_reason": tr["end_reason"]})
stats["kept"] = len(out)
p = ROOT / "runs/A12/sft_data.jsonl"
p.parent.mkdir(parents=True, exist_ok=True)
with open(p, "w") as fh:
    for x in out:
        fh.write(json.dumps(x) + "\n")
lens = sorted(len(x["prompt_ids"]) + len(x["completion_ids"]) for x in out)
stats["tokens_median"] = lens[len(lens) // 2] if lens else 0
stats["tokens_max"] = lens[-1] if lens else 0
json.dump(stats, open(ROOT / "results/A12/sft_data_stats.json", "w"), indent=1)
print(stats)
