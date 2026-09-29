"""A10 aggregate: per-task verdicts from records, reference reports and blind reviews. Works on partial data."""
import glob, json
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "results/A10"
sample = json.load(open(OUT / "sample.json"))["tasks"]
rev = {r["key"]: r for f in sorted(glob.glob(str(OUT / "reviews/review_*.json"))) for r in json.load(open(f))}
refrep = {r["key"]: r for f in sorted(glob.glob(str(OUT / "refs_report_*.json"))) for r in json.load(open(f))}


def verdict(key: str) -> tuple[str, list[str]]:
    rec = json.loads((OUT / "records" / f"{key}.json").read_text())
    if not rec["build"]["ok"]:
        return "not admissible", ["build_fail"]
    why = []
    if rec["noop"]["pass"]:
        why.append("noop_passes")
    if not all(g["pass"] for g in rec["gold"]):
        why.append("gold_fail")
    if why:
        return "not admissible", why
    if "reference" not in rec or key not in rev:
        return "pending", []
    if not rec["reference"]:
        why.append("UNVERIFIED")
    elif not all(x["grade"]["pass"] for x in rec["reference"]):
        why.append("ref_fail")
    if rec.get("mutant") and rec["mutant"]["grade"]["pass"]:
        why.append("mutant_accepted")
    v = rev[key]
    if v["verdict"] != "valid":
        why.append("review_" + v["verdict"])
    if any(d.get("confirmed") and d["type"] == "answer_exposure" for d in v["defects"]):
        why.append("EXPOSURE")
    if v.get("safety") != "ok":
        why.append("safety_concern")
    return ("admissible" if not why else "not admissible"), why


rows = {t["key"]: verdict(t["key"]) for t in sample}
n = Counter(v for v, _ in rows.values())
defects = Counter(d["type"] for v in rev.values() for d in v["defects"] if d.get("confirmed"))
reasons = Counter(w for _, ws in rows.values() for w in ws)
decided = n["admissible"] + n["not admissible"]
summ = {"n": len(rows), "admissible": n["admissible"], "not_admissible": n["not admissible"], "pending": n["pending"],
        "max_possible_admissible": n["admissible"] + n["pending"], "reasons": dict(reasons), "confirmed_defects": dict(defects),
        "per_task": {k: {"verdict": v, "why": w} for k, (v, w) in rows.items()}}
json.dump(summ, open(OUT / "summary.json", "w"), indent=1)
print(json.dumps({k: v for k, v in summ.items() if k != "per_task"}, indent=1))
for k, (v, w) in rows.items():
    print(f"{k[8:72]:64} {v:15} {','.join(w)}")
