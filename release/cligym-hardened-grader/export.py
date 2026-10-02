"""Build the public release folder from the private results (measurements only; host paths scrubbed)."""
import json, re, shutil
from pathlib import Path

REPO = Path("/mnt/sdb/arafat/ehz/llm/terminal-recovery-rl")
R = Path(__file__).resolve().parent
OUT = R / "pub"
SCRUB = [(re.compile(r"/tmp/claude-[^\s'\"]*"), "<scratch>"), (re.compile(r"/mnt/sdb/[^\s'\"]*"), "<local path>"),
         (re.compile(r"scripts/a1\d_\w+\.py"), "the audit harness"), (re.compile(r"--explore"), "an interactive probe"),
         (re.compile(r"--try"), "a graded attempt"), (re.compile(r"\brefs?/|\bmutants/"), "")]


def scrub(x):
    if isinstance(x, str):
        for pat, rep in SCRUB:
            x = pat.sub(rep, x)
        return x
    if isinstance(x, list):
        return [scrub(v) for v in x]
    if isinstance(x, dict):
        return {k: scrub(v) for k, v in x.items()}
    return x


REASON = {"mutant_accepted": "wrong_answer_accepted", "review_defective": "reviewer_found_defects",
          "EXPOSURE": "answer_exposed_to_agent", "gold_fail": "gold_image_fails_own_tests", "build_fail": "image_does_not_build",
          "noop_passes": "untouched_container_passes", "ref_fail": "reference_repair_fails", "UNVERIFIED": "no_reference_repair"}
NAMES = {"base": "base_9b", "sft_a12": "sft_72_demos", "sft_a13": "sft_371_demos", "teacher": "teacher_27b"}


def tid(key):
    return key[8:] if key.startswith("CLIGym__") else key


def dump(rel, obj):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(scrub(obj), indent=1, ensure_ascii=False) + "\n")


shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir()

# 1. audit of 24 sampled tasks
sample = json.load(open(REPO / "results/A10/sample.json"))["tasks"]
rev = {r["key"]: r for f in sorted((REPO / "results/A10/reviews").glob("review_*.json")) for r in json.load(open(f))}
summ = json.load(open(REPO / "results/A10/summary.json"))["per_task"]
rows = []
for t in sample:
    rec = json.load(open(REPO / f"results/A10/records/{t['key']}.json"))
    g = lambda x: x["grade"]["pass"] if x else None
    verdict = {"pending": "not_completed", "not admissible": "not_admissible", "admissible": "admissible"}[summ[t["key"]]["verdict"]]
    row = {"task_id": tid(t["key"]), "verdict": verdict, "repository_image": t["base"], "builds": rec["build"]["ok"],
           "untouched_container_fails": (not rec["noop"]["pass"]) if rec.get("noop") else None,
           "gold_image_passes": [x["pass"] for x in rec.get("gold", [])],
           "reference_repair_passes": [g(x) for x in rec["reference"]] if rec.get("reference") else None,
           "wrong_answer_accepted_by_dataset_grader": g(rec.get("mutant")),
           "not_admissible_reasons": [REASON.get(w, w) for w in summ[t["key"]]["why"]]}
    if t["key"] in rev:
        v = rev[t["key"]]
        row["review"] = {"verdict": v["verdict"], "realism_1to5": v.get("realism"),
                         "defects": [{"type": d["type"], "confirmed": d.get("confirmed"), "evidence": d.get("evidence")} for d in v["defects"]],
                         "wrong_answer_intent": v.get("mutant_intent")}
    rows.append(row)
dump("audit/tasks.json", rows)
for f in (REPO / "results/A10/refs").glob("*.sh"):
    (OUT / "audit/reference_repairs").mkdir(parents=True, exist_ok=True)
    (OUT / "audit/reference_repairs" / (tid(f.stem) + ".sh")).write_text(scrub(f.read_text()))
for f in (REPO / "results/A10/mutants").glob("*.sh"):
    (OUT / "audit/wrong_answers").mkdir(parents=True, exist_ok=True)
    (OUT / "audit/wrong_answers" / (tid(f.stem) + ".sh")).write_text(scrub(f.read_text()))

# 2. grader validation with the released grader.py
val = {}
for f in sorted((R / "validation").glob("*.json")):
    if f.stat().st_size == 0:
        continue
    k, kind = f.stem.rsplit("__", 1)
    r = json.load(open(f))
    val.setdefault(k, {})[kind] = {"dataset_grader": r["dataset_grader"]["pass"], "hardened": r["hardened"]["pass"],
                                    "residue": r["hardened"]["residue"][:5], "tests_summary": r["hardened"]["tests"]["summary"]}
dump("validation/grader_validation.json", val)

# 3. base model with both graders (46 tasks x 4 attempts)
hs = json.load(open(REPO / "results/A11/headroom_summary.json"))
excl = set(hs["sensitivity_without_vacuous_tasks"]["excluded"])
dump("model_results/base_model_both_graders.json", {
    "setup": "Qwen3.5-9B instruct, prompts/system_prompt.txt, 4 attempts per task, at most 30 bash commands, 32K context, offline container",
    "per_task_passes_of_4": {tid(k): {"dataset_grader": hs["v1_per_task"][k], "hardened": hs["v2_per_task"][k],
                                      "inert_damage": k in excl} for k in hs["v2_per_task"]}})
rv = json.load(open(REPO / "results/A11/v2_pass_review.json"))
dump("model_results/hardened_pass_review.json", [{"task_id": tid(x["key"]), "attempt": x["i"], "genuine_repair": x["genuine"],
                                                  "reason": x["reason"]} for x in rv])

# 4. SFT
test = json.load(open(REPO / "results/A12/test_tasks.json"))
s12 = json.load(open(REPO / "results/A12/sft_test_summary.json"))["sft_per_task"]
s13 = json.load(open(REPO / "results/A13/sft_test_summary.json"))
te = json.load(open(REPO / "results/A12/teacher_test_summary.json"))["teacher_per_task"]
keys = sorted(set(test["base_v2_per_task"]) & set(s12) & set(s13["sft_a13_per_task"]) & set(te))
dump("model_results/sft_heldout.json", {
    "metric": "hardened-grader passes out of 4 attempts per held-out task",
    "per_task": {tid(k): {"base": test["base_v2_per_task"][k], "sft_72_demos": s12[k], "sft_371_demos": s13["sft_a13_per_task"][k],
                          "teacher_27b": te[k]} for k in keys},
    "summary": {"tasks": len(keys), "mean_pass_rate": {NAMES[k]: v for k, v in s13["summary"]["mean"].items()},
                "mixed_tasks_1_to_3_of_4": {NAMES[k]: v for k, v in s13["summary"]["mixed"].items()},
                                         "paired_diff_95ci": {"sft_371_vs_base": s13["summary"]["a13_vs_base"][:2],
                                                              "sft_371_vs_sft_72": s13["summary"]["a13_vs_a12"][:2],
                                                              "sft_72_vs_base": s13["summary"]["a12_vs_base_same_tasks"][:2]}}})
shutil.copy(REPO / "prompts/p7_cligym_repair.txt", OUT / "system_prompt.txt")
shutil.copy(R / "grader.py", OUT / "grader.py")
shutil.copy(R / "README.md", OUT / "README.md")
print("exported", sum(1 for _ in OUT.rglob("*") if _.is_file()), "files")
