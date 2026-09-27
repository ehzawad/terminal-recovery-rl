import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
import ast,collections,hashlib,json,re,shutil
from pathlib import Path
import pyarrow.parquet as pq
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
OUT=Path(__file__).resolve().parent
POOL=Path('/mnt/sdb/arafat/ehz/llm/.pools/endless-terminals')
rows=[json.loads(s) for s in (OUT/'endless_refined_inventory.jsonl').read_text().splitlines()]
def flat(s):return ' '.join(s.split())
for r in rows:
    matches=[]
    if r['semantic_eligible']:
        try:tree=ast.parse((POOL/r['id']/'tests/test_final_state.py').read_text())
        except SyntaxError:tree=None
        if tree:
            for n in ast.walk(tree):
                if not isinstance(n,(ast.Assign,ast.AnnAssign)):continue
                names=[ast.unparse(x) for x in n.targets] if isinstance(n,ast.Assign) else [ast.unparse(n.target)]
                if not any('expected' in x.lower() for x in names):continue
                try:v=ast.literal_eval(n.value)
                except Exception:continue
                if isinstance(v,list) and all(isinstance(x,str) for x in v):v='\n'.join(v)
                if isinstance(v,bytes):v=v.decode(errors='replace')
                if not isinstance(v,str) or len(v)<40 or len(v.strip().splitlines())<2:continue
                if flat(v) in flat(r['instruction']):matches.append({'variable':names,'bytes':len(v)})
    r['literal_expected_block_in_prompt']=matches
    r['static_final']=r['semantic_eligible'] and not matches

eligible=[r for r in rows if r['static_final']]
x=TfidfVectorizer(ngram_range=(1,2),min_df=2,max_df=.95,sublinear_tf=True).fit_transform(r['normalized_instruction'] for r in rows)
edges=[]
for start in range(0,len(rows),100):
    m=cosine_similarity(x[start:start+100],x,dense_output=False).tocoo()
    edges.extend((start+int(i),int(j),float(s)) for i,j,s in zip(m.row,m.col,m.data) if start+i<j and s>=.5)
counts={};cluster_maps={}
for threshold in [.5,.6,.7,.8]:
    parent=list(range(len(rows)))
    def root(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    for i,j,s in edges:
        if s>=threshold:
            a,b=root(i),root(j)
            if a!=b:parent[max(a,b)]=min(a,b)
    maps={r['id']:rows[root(i)]['id'] for i,r in enumerate(rows)}
    groups=collections.defaultdict(list)
    for r in eligible:groups[maps[r['id']]].append(r['id'])
    counts[str(threshold)]={'clusters':len(groups),'largest_groups':sorted(groups.values(),key=len,reverse=True)[:5]}
    cluster_maps[str(threshold)]=maps

# Use 0.60 as conservative candidate clustering; this is not a proof of independence.
maps=cluster_maps['0.6']
for r in rows:r['candidate_lineage']=maps[r['id']]
uniq={}
for r in sorted(eligible,key=lambda r:r['id']):uniq.setdefault(maps[r['id']],r)
def p(r,m):return r['rates'][m]['s']/r['rates'][m]['n']
def bucket(r):return '12-14/16' if p(r,'o3')<15/16 else '15/16' if p(r,'o3')<1 else '16/16'
summary={'semantic_candidates':sum(r['semantic_eligible'] for r in rows),'literal_block_exclusions':sum(bool(r['literal_expected_block_in_prompt']) for r in rows),'final_task_ids':len(eligible),'candidate_lineages':len(uniq),'o3_by_lineage':dict(collections.Counter(bucket(r) for r in uniq.values())),'paired_rates_lineages':sum('llama3b'in r['rates'] for r in uniq.values()),'similarity_sensitivity':counts,'definitions':'Candidate lineage = connected component at word 1/2-gram TF-IDF cosine >=0.60 after path and number normalization; no verified generator-parent field exists.'}
(OUT/'endless_final_static_stats.json').write_text(json.dumps(summary,indent=2))
with (OUT/'endless_final_inventory.jsonl').open('w') as f:
    for r in rows:f.write(json.dumps(r)+'\n')
(OUT/'endless_near_pairs.json').write_text(json.dumps([{'a':rows[i]['id'],'b':rows[j]['id'],'cosine':s} for i,j,s in sorted(edges,key=lambda e:-e[2])],indent=2))
(OUT/'endless_final_candidate_ids.json').write_text(json.dumps([r['id'] for r in eligible],indent=2))

tm=pq.read_table(OUT/'tmax_harbor.parquet').to_pylist();cc={r['task_id']:r for r in pq.read_table(OUT/'tmax_canonical_audit_columns.parquet').to_pylist()}
ids=set(json.loads((OUT/'tmax_static_candidate_ids.json').read_text()));trows=[r for r in tm if r['task_id'] in ids]
bad=r'\b(?:compiled|compiler|linker|compil\w*|gdb|strace|ltrace|ELF|C\+\+|C source|memory dump|packet capture|pcap|encrypted|encryption|decrypt\w*)\b|pip(?:3)?\s+install|requirements\.txt|\bpandas\b|\bnumpy\b'
filtered=[r for r in trows if not re.search(bad,r['instruction'],re.I)]
rep=[r for r in filtered if re.search(r'\b(?:repair|fix|debug|broken|bug|bugs|failing|incorrect|malformed|crashes|exception|regression)\b',r['instruction'],re.I)]
leaks=[]
basic=[r for r in tm if r['domain'] in ['debugging','data_processing'] and r['language'] in ['Python','Bash'] and r['task_complexity'].startswith(('short','moderate'))]
for r in basic:
    c=cc[r['task_id'].removeprefix('tmax/')]
    if '.truth.' in c['container_def'] and '.truth.' in c['test_final_state']:leaks.append(r['task_id'])
tstat={'initial_static_candidates':len(trows),'no_binary_crypto_runtime_dependency_candidates':len(filtered),'repair_text_candidates':len(rep),'complexity':dict(collections.Counter(r['task_complexity'].split()[0] for r in rep)),'truth_file_written_and_used_by_verifier':len(leaks),'truth_file_task_ids':leaks}
(OUT/'tmax_refined_stats.json').write_text(json.dumps(tstat,indent=2));(OUT/'tmax_refined_ids.json').write_text(json.dumps([r['task_id'] for r in rep],indent=2))

sa=json.loads((OUT/'seta_service_audit.json').read_text());base=collections.Counter();net=0;offline_text=[]
for id in sa['sample_ids']:
    d=next((OUT/'samples/seta').glob('*/'+id));df=(d/'environment/Dockerfile').read_text();ts=(d/'tests/test.sh').read_text();base.update(re.findall(r'(?im)^FROM\s+(\S+)',df));net+=bool(re.search(r'\b(?:uvx|curl|wget|pip install|pip3 install|uv pip)\b',ts))
    ins=(d/'instruction.md').read_text();
    if not re.search(r'https?://|\b(?:apt(?:-get)? install|pip install|download|internet)\b',ins,re.I):offline_text.append(id)
sstat={'sample_tasks':len(sa['sample_ids']),'sample_roots':sa['sample_roots'],'base_images':dict(base),'runtime_verifier_installer_or_fetch_commands':net,'instructions_without_obvious_network_or_install_requirement':len(offline_text),'offline_candidate_ids':offline_text}
(OUT/'seta_sample_stats.json').write_text(json.dumps(sstat,indent=2))
print('ENDLESS',json.dumps(summary,indent=2));print('TMAX',json.dumps(tstat,indent=2));print('SETA',json.dumps(sstat,indent=2))
