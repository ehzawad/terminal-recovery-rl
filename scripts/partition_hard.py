"""Model-free admission and the frozen partition of Study 3 (amendments A8, A8.1). Uses no Qwen output.

Admitted = valid in data/hard/validity.jsonl (clean validity gate) AND verifier discrimination passed AND
not excluded by the instruction-verifier review (data/hard/review/batch_*.json). Admitted tasks related
by the near-duplicate adjudication (data/hard/review/near_duplicates.json) form one group. Groups sorted
by sha256('hard1:'+group_id), group_id = the group's smallest task id, fill test 48, gate 16, checkpoint
16, prompt-search 16; the rest are train; groups holding a task Qwen saw before are placed in train and
skipped by the sorted assignment. Fewer than 144 groups -> stop.

Writes data/hard/admission.json (per-task decisions), data/hard/partitions.json, data/hard/split.json
(make_rows --split format), data/hard/test_labels.json and, through freeze_contracts.py,
data/hard/contracts.jsonl. Refuses to overwrite an existing partition.

Usage: python scripts/partition_hard.py
"""

import glob
import hashlib
import json
import os
import subprocess
import sys

SIZES = [("test", 48), ("gate", 16), ("checkpoint", 16), ("search", 16)]
MIN_GROUPS = 144


def main() -> None:
    if os.path.exists("data/hard/partitions.json"):
        sys.exit("data/hard/partitions.json exists: the Study 3 partition is already frozen")
    cands = json.load(open("data/hard/candidates.json"))
    exposed = set(cands["exposed_to_qwen_before"])
    validity = {}
    for line in open("data/hard/validity.jsonl"):
        r = json.loads(line)
        validity[r["task_id"]] = r
    review = {}
    for f in sorted(glob.glob("data/hard/review/batch_*.json")):
        review.update(json.load(open(f))["tasks"])
    missing = [t for t in cands["candidates"] if t not in validity or t not in review]
    if missing:
        sys.exit(f"{len(missing)} candidates lack a validity record or a review: {missing[:5]}")
    decisions, admitted = {}, []
    for t in cands["candidates"]:
        v, rv = validity[t], review[t]
        d = {"valid": bool(v.get("valid")), "harness_error": bool(v.get("harness_error")),
             "discrimination": (v.get("discrimination") or {}).get("pass"),
             "review_exclude": bool(rv["exclude"]), "review_reasons": rv.get("reasons", [])}
        d["admitted"] = d["valid"] and d["discrimination"] is True and not d["review_exclude"]
        decisions[t] = d
        if d["admitted"]:
            admitted.append(t)
    parent = {t: t for t in admitted}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    related_easy = {}
    for p in json.load(open("data/hard/review/near_duplicates.json"))["pairs"]:
        if not p["related"]:
            continue
        a, b = p["a"], p["b"]
        if a in parent and b in parent:
            parent[find(a)] = find(b)
        elif a in parent:
            related_easy.setdefault(a, []).append(b)
    groups = {}
    for t in admitted:
        groups.setdefault(find(t), []).append(t)
    groups = {min(m): sorted(m) for m in groups.values()}
    record = {"candidates": len(cands["candidates"]), "admitted_tasks": len(admitted), "groups": len(groups),
              "min_groups": MIN_GROUPS, "decisions": decisions, "related_to_easy_tasks": related_easy}
    json.dump(record, open("data/hard/admission.json", "w"), indent=1)
    if len(groups) < MIN_GROUPS:
        print(json.dumps({k: v for k, v in record.items() if k != "decisions"}, indent=1))
        sys.exit(f"STOP: {len(groups)} admitted groups < {MIN_GROUPS} (A8)")
    exp_groups = sorted(g for g, m in groups.items() if exposed & set(m))
    order = sorted((g for g in groups if g not in exp_groups),
                   key=lambda g: hashlib.sha256(f"hard1:{g}".encode()).hexdigest())
    roles, i = {}, 0
    for role, n in SIZES:
        roles[role] = order[i:i + n]
        i += n
    roles["train"] = order[i:] + exp_groups
    parts = {role: sorted(t for g in gs for t in groups[g]) for role, gs in roles.items()}
    parts["groups"] = {role: len(gs) for role, gs in roles.items()}
    parts["rule"] = __doc__.split("\n\n")[1].replace("\n", " ")
    json.dump(parts, open("data/hard/partitions.json", "w"), indent=1)
    json.dump({"rule": "Study 3 roles (A8)", "assignments": {t: f"h_{role}" for role in roles for t in parts[role]}},
              open("data/hard/split.json", "w"), indent=1)
    json.dump({t: review[t].get("tests", {}) for t in admitted}, open("data/hard/test_labels.json", "w"), indent=1)
    json.dump(admitted, open("data/hard/admitted.json", "w"), indent=1)
    subprocess.run([sys.executable, "scripts/freeze_contracts.py", "--validity", "data/hard/validity.jsonl",
                    "--ids", "data/hard/admitted.json", "--out", "data/hard/contracts.jsonl"], check=True)
    print(json.dumps({"admitted_tasks": len(admitted), "groups": len(groups), "exposed_groups": len(exp_groups),
                      "roles": parts["groups"], "tasks_per_role": {r: len(parts[r]) for r in roles},
                      "related_to_easy_tasks": len(related_easy)}, indent=1))


if __name__ == "__main__":
    main()
