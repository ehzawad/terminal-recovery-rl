"""A9 aggregate: combine executable records, blind reviews and the static screen into per-task verdicts."""
import glob, json, collections
from pathlib import Path
R = Path(__file__).resolve().parents[1] / "results" / "A9"
rec = {json.load(open(f))["key"]: json.load(open(f)) for f in glob.glob(str(R / "records/*.json"))}
rev = {r["key"]: r for f in sorted(glob.glob(str(R / "reviews/review_*.json"))) for r in json.load(open(f))}
stat = json.load(open(R / "static_screen.json"))["per_task"]

def cls(k):
    d, v, s = rec[k], rev[k], stat[k]
    why = []
    b = d.get("build", {}).get("ok")
    if d.get("status") == "harness_error": why.append("harness_error")
    if not b: why.append("build_fail")
    noop = (d.get("noop") or {}).get("pass")
    if noop: why.append("noop_passes")
    if d["ds"] == "TMax" and not (d.get("initial_state") or {}).get("pass"): why.append("initial_state_fail")
    refs = d.get("ref") or []
    if d["ds"] == "TMax":
        if refs and refs[0].get("how") == "none": why.append("UNVERIFIED")
        elif not (len(refs) >= 2 and all((x.get("grade") or {}).get("pass") for x in refs)): why.append("ref_fail")
    else:
        if not (len(refs) >= 2 and all((x.get("grade") or {}).get("pass") for x in refs)): why.append("ref_fail")
    m = d.get("mutant")
    if m and (m.get("grade") or {}).get("pass"):
        why.append("mutant_accepted" if v.get("must_reject") else "mutant_passes_but_arguably_valid")
    if v["verdict"] != "valid": why.append("review_" + v["verdict"])
    if any(x["confirmed"] and x["type"] == "answer_exposure" for x in v["defects"]): why.append("EXPOSURE")
    if v["safety"] != "ok": why.append("safety_concern")
    return why

rows = {}
for k in rec:
    why = cls(k)
    rows[k] = why
    print(k[:62].ljust(62), "ADMISSIBLE" if not why else ",".join(why))
by = collections.defaultdict(list)
for k, w in rows.items(): by[rec[k]["ds"]].append((k, w))
summary = {}
for ds, xs in by.items():
    n = len(xs); adm = sum(1 for _, w in xs if not w)
    exp = sum(1 for _, w in xs if "EXPOSURE" in w)
    unv = sum(1 for _, w in xs if "UNVERIFIED" in w)
    summary[ds] = {"n": n, "admissible": adm, "exposure": exp, "unverified": unv,
                   "reviewer_valid": sum(1 for k, _ in xs if rev[k]["verdict"] == "valid"),
                   "ref_pass_2x": sum(1 for k, w in xs if "ref_fail" not in w and "UNVERIFIED" not in w and "build_fail" not in w),
                   "mutant_accepted": sum(1 for _, w in xs if "mutant_accepted" in w),
                   "noop_passes": sum(1 for _, w in xs if "noop_passes" in w)}
    if ds == "TMax":
        ver = n - unv
        summary[ds]["verifiable_n"] = ver
        summary[ds]["admissible_frac_all"] = round(adm / n, 3)
        summary[ds]["admissible_frac_verifiable"] = round(adm / ver, 3) if ver else None
    else:
        summary[ds]["admissible_frac"] = round(adm / n, 3)
print(json.dumps(summary, indent=1))
json.dump({"per_task": {k: {"admissible": not w, "reasons": w} for k, w in rows.items()}, "per_dataset": summary}, open(R / "summary.json", "w"), indent=1)
