"""Read-only council calculations. No containers, model calls, or training.

Candidate counts are static screens, not runtime-valid task counts.
Power is a normal-approximation sensitivity calculation, not observed power.
"""
import ast
import collections
import hashlib
import json
import math
import re
from pathlib import Path
from statistics import NormalDist

REPO = Path('/mnt/sdb/arafat/ehz/llm/terminal-recovery-rl')
AUDIT = Path('/tmp/codex-council.5eXia3/scout-audit')
POOL = Path('/mnt/sdb/arafat/ehz/llm/.pools/endless-terminals')
rows = [json.loads(s) for s in (AUDIT / 'endless_refined_inventory.jsonl').read_text().splitlines()]
bad = {'runtime_network_text', 'service_or_heavy_text', 'weak_verifier_static',
       'answer_file_suspect', 'copy_entire_context', 'nonstdlib_test_import', 'other_base'}
hard = [r for r in rows if r['rates']['o3']['s'] <= 11]
local = [r for r in hard if r['topic'] and not bad.intersection(r['flags'])]
semantic = [r for r in local if r['semantic_text'] and not r['dynamic_time'] and not r['literal_answer_text']]

def literal_block(r):
    tree = ast.parse((POOL / r['id'] / 'tests/test_final_state.py').read_text())
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any('expected' in ast.unparse(t).lower() for t in targets):
            continue
        try:
            value = ast.literal_eval(node.value)
        except Exception:
            continue
        if isinstance(value, list) and all(isinstance(x, str) for x in value):
            value = '\n'.join(value)
        if isinstance(value, bytes):
            value = value.decode(errors='replace')
        if isinstance(value, str) and len(value) >= 40 and len(value.strip().splitlines()) >= 2:
            if ' '.join(value.split()) in ' '.join(r['instruction'].split()):
                return True
    return False

post_literal = [r for r in semantic if not literal_block(r)]
task_ast = ast.parse((REPO / 'termrl/tasks.py').read_text())
exec_regex = next(ast.literal_eval(n.value.args[0]) for n in task_ast.body
                 if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_EXEC' for t in n.targets))
post_a6 = [r for r in post_literal if not re.search(exec_regex, (POOL / r['id'] / 'tests/test_final_state.py').read_text())]

def packages(task_id):
    text = (POOL / task_id / 'environment/Dockerfile').read_text().replace('\\\n', ' ')
    return {x for line in re.findall(r'apt(?:-get)?\s+install\b([^;&\n]+)', text)
            for x in line.split() if not x.startswith('-')}

old_exclusions = json.loads((AUDIT / 'endless_package_exclusions.json').read_text())
banned = {p for r in old_exclusions for p in r['packages']}
old_candidates = json.loads((AUDIT / 'endless_final_candidate_ids.json').read_text())
assert {t for t in old_candidates if packages(t) & banned} == {r['id'] for r in old_exclusions}
post_packages = [r for r in post_a6 if not packages(r['id']) & banned]
old_admitted = json.loads((AUDIT / 'endless_recommended_ids.json').read_text())
observed_allowed = {p for t in old_admitted for p in packages(t)}
unseen = {r['id']: sorted(packages(r['id']) - observed_allowed) for r in post_packages
          if packages(r['id']) - observed_allowed}
mismatches = []
for r in rows:
    for file, key in [('instruction.md', 'instruction_hash'), ('tests/test_final_state.py', 'test_hash')]:
        if hashlib.sha256((POOL / r['id'] / file).read_bytes()).hexdigest() != r[key]:
            mismatches.append({'task': r['id'], 'file': file, 'o3_successes': r['rates']['o3']['s']})
summary_disagreements = sum(json.loads((POOL / r['id'] / 'solution/o3_summary.json').read_text())['num_success']
                            != r['rates']['o3']['s'] for r in rows)

normal = NormalDist()
power = []
for n in [36, 40, 48, 60, 89, 100]:
    for q in [.2, .4, .6]:
        for rho in [0, .5, 1]:
            delta = .12
            variance = (q - delta**2) * (rho + (1-rho)/4)
            se = math.sqrt(variance/n)
            threshold = max(.12, .03 + normal.inv_cdf(.9)*se)
            power.append({'tasks': n, 'paired_discordance': q, 'contrast_icc': rho, 'trials_per_task': 4,
                          'true_delta': delta, 'se': se,
                          'power_ci_clause_only': normal.cdf(.09/se-normal.inv_cdf(.9)),
                          'power_both_numeric_clauses_one_control': 1-normal.cdf((threshold-delta)/se)})

out = {'measurement_boundary': 'Static screening only; no runtime validity, manual semantic audit, model calls, or training.',
       'counts': {'all': len(rows), 'o3_le11': len(hard), 'local_hard': len(local),
                  'semantic_hard': len(semantic), 'after_literal': len(post_literal),
                  'after_a6_before_packages': len(post_a6), 'after_reconstructed_package_exclusion': len(post_packages),
                  'also_rejecting_unseen_apt_packages': len(post_packages)-len(unseen)},
       'inventory_hash_mismatches': mismatches, 'o3_summary_disagreements': summary_disagreements,
       'package_reproduction_note': 'Denylist inferred from old exclusions reproduces all 46 old exclusions exactly; not a complete new-task dependency audit.',
       'unseen_apt_packages': unseen, 'static_candidate_ids': [r['id'] for r in post_packages],
       'power_assumptions': 'Paired contrast D in {-1,0,1}; E[D]=.12; P[D!=0]=q. Four repeats with assumed contrast ICC rho. Normal percentile-CI approximation with z(.90), matching two-sided central 80% CI. Not actual bootstrap simulation.',
       'power_sensitivity': power,
       'compute_arithmetic': {'old_smoke_seconds_16_trajectories': 699.3,
                              'naive_1024_trajectory_hours': 699.3/16*1024/3600,
                              'required_max_seconds_per_trajectory_for_14_hours': 14*3600/1024,
                              'final_episodes_48_hard_x4_plus147_easy_x2_four_arms': 1944,
                              'ideal_final_hours_at_48_9_sec_and8_workers': 1944*48.9/8/3600}}
target = Path('/tmp/council-r7-root-evidence.json')
target.write_text(json.dumps(out, indent=2)+'\n')
print(json.dumps({k: out[k] for k in ['measurement_boundary', 'counts', 'inventory_hash_mismatches', 'o3_summary_disagreements', 'compute_arithmetic']}, indent=2))
print('Full evidence:', target)
