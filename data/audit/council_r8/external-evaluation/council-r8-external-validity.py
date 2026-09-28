from pathlib import Path
from collections import Counter
from statistics import NormalDist
import json, math, re, tomllib
import numpy as np
ROOT = Path('/mnt/sdb/arafat/ehz/llm/.pools')
report = {'boundary':'Static source inspection and synthetic power calculations only. No model, container, or benchmark solution run.'}
for name,root in [('tblite',ROOT/'tblite'),('tb21',ROOT/'tb21/tasks')]:
    ps=sorted(p for p in root.iterdir() if (p/'task.toml').is_file())
    docs=[tomllib.loads((p/'task.toml').read_text()) for p in ps]
    naive=[]; install_free=[]; wrappers=[]
    for p in ps:
        sh=(p/'tests/test.sh').read_text()
        if not re.search(r'uvx|pip\s+install|pip3\s+install|curl\s|wget\s|apt-get\s',sh): naive.append(p)
        if not re.search(r'uvx|pip\s+install|pip3\s+install|curl\s+-Ls|apt-get\s',sh): install_free.append(p)
        f=p/'tests/test_outputs.py'
        if f.is_file() and 'regardless of score' in f.read_text() and 'assert True' in f.read_text(): wrappers.append(p)
    report[name]={
        'tasks':len(ps),
        'internet_flags':dict(Counter(str(d.get('environment',{}).get('allow_internet','unset')) for d in docs)),
        'naive_no_network_command_count':len(naive),
        'no_obvious_installs_count':len(install_free),
        'difference_ids':[p.name for p in install_free if p not in naive],
        'pytest_wrapper_passes_regardless_of_score':len(wrappers),
        'naive_subset_with_wrapper':len(set(naive)&set(wrappers)),
        'raw_difficulty_all':dict(Counter(d['metadata']['difficulty'] for d in docs)),
        'raw_difficulty_naive_subset':dict(Counter(tomllib.loads((p/'task.toml').read_text())['metadata']['difficulty'] for p in naive)),
        'sum_agent_timeout_seconds':sum(d['agent']['timeout_sec'] for d in docs),
        'naive_subset_sum_agent_timeout_seconds':sum(tomllib.loads((p/'task.toml').read_text())['agent']['timeout_sec'] for p in naive),
        'candidate_ids':[p.name for p in naive]
    }
# Exact probability of clearing point gain >= .12 and the infinite-resample
# percentile task bootstrap 10th percentile > .03, for one binary attempt/task.
# W=R-only successes, L=control-only successes; P(W)= (q+delta)/2.
# This is a sensitivity model, not a forecast. Tasks independent, identically
# distributed; no training seed variation; one comparison, no other guardrails.
rows=[]
for n in (40,44,60,90):
    configs=[]
    for w in range(n+1):
        for l in range(n-w+1):
            if (w-l)/n < .12-1e-12: continue
            probs=np.array([l/n,(n-w-l)/n,w/n])
            dist=np.array([1.0])
            for _ in range(n): dist=np.convolve(dist,probs)
            # support [-n,n], exact CDF at .03*n rounded down
            cdf=dist[:n+math.floor(.03*n)+1].sum()
            accepted=cdf < .10
            coeff=math.lgamma(n+1)-math.lgamma(w+1)-math.lgamma(l+1)-math.lgamma(n-w-l+1)
            configs.append((w,l,n-w-l,coeff,accepted))
    for q in (.2,.4,.6):
        for delta in (.107,.12,.20):
            pp,pm,pz=(q+delta)/2,(q-delta)/2,1-q
            total=0.; point=0.
            for w,l,z,coef,accepted in configs:
                if (pp==0 and w) or (pm==0 and l) or (pz==0 and z): continue
                lp=coef+sum(c*math.log(p) for c,p in [(w,pp),(l,pm),(z,pz)] if c)
                prob=math.exp(lp)
                point+=prob
                if accepted: total+=prob
            rows.append({'n':n,'discordance_q':q,'true_delta':delta,'power_point_only':round(point,5),'power_both':round(total,5)})
report['exact_one_attempt_power']=rows
normal=NormalDist()
report['four_attempt_approximation']=[]
for n in (40,44,60,90):
    for rho in (0,.5,1):
        for delta in (.107,.12,.20):
            q=.4
            se=math.sqrt((q-delta**2)*(rho+(1-rho)/4)/n)
            cutoff=max(.12,.03+normal.inv_cdf(.9)*se)
            power=1-normal.cdf((cutoff-delta)/se)
            report['four_attempt_approximation'].append({'n':n,'contrast_ICC':rho,'true_delta':delta,'SE':se,'power':power})
Path('/tmp/council-r8-external-validity.json').write_text(json.dumps(report,indent=2)+'\n')
for name in ('tblite','tb21'):
    print(name,json.dumps({k:v for k,v in report[name].items() if k!='candidate_ids'}))
print('EXACT one attempt per task, q=.4')
for row in rows:
    if row['discordance_q']==.4: print(row)
print('APPROX four attempts, q=.4, contrast ICC=.5')
for row in report['four_attempt_approximation']:
    if row['contrast_ICC']==.5: print({k:round(v,5) if isinstance(v,float) else v for k,v in row.items()})
