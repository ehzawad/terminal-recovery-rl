import ast, collections, hashlib, json, re, sys
from pathlib import Path
import tomli
import pyarrow.parquet as pq

OUT = Path(__file__).resolve().parent
ET = Path('/mnt/sdb/arafat/ehz/llm/.pools/endless-terminals')
def read(p): return p.read_text(errors='replace') if p.exists() else ''
def h(s): return hashlib.sha256(s.encode()).hexdigest()
def norm(s):
    s=s.lower()
    s=re.sub(r'task_\d+_[a-f0-9]+', 'TASK', s)
    s=re.sub(r'(?<!\w)/(?:[\w.~-]+/)*[\w.~-]+', '/PATH', s)
    s=re.sub(r'\b\d+(?:\.\d+)?\b', 'NUM', s)
    return ' '.join(s.split())
NETWORK = r'https?://|\b(?:requests|urllib|socket|wget)\b|\bcurl\s'
HEAVY = r'\b(?:docker|kubectl|kubernetes|systemctl|postgresql|mysql|nginx|apache2|ffmpeg|tesseract|cuda|gpu|tensorflow|torch)\b'
REPAIR = r'\b(?:repair|fix|debug|broken|bug|bugs|failing|incorrect|malformed|crashes|exception|regression)\b'
TOPIC = r'\b(?:script|scripts|pipeline|parser|parsing|csv|json|jsonl|log|logs|configuration|config|data|files|directory)\b'
def test_features(s):
    try: tree=ast.parse(s)
    except SyntaxError: return {'syntax_error':True,'assertions':0,'test_functions':0,'imports':[],'presence_only':False}
    asserts=[n for n in ast.walk(tree) if isinstance(n,ast.Assert)]
    fs=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test')]
    imports=[]
    for n in ast.walk(tree):
        if isinstance(n,ast.Import): imports.extend(x.name.split('.')[0] for x in n.names)
        elif isinstance(n,ast.ImportFrom): imports.append((n.module or '').split('.')[0])
    astr=[ast.unparse(a.test) for a in asserts]
    return {'syntax_error':False,'assertions':len(asserts),'test_functions':len(fs),'imports':sorted(set(imports)),
            'presence_only':bool(astr) and all(re.search(r'\.exists\(|\.is_file\(|\.is_dir\(|os\.path\.(?:exists|isfile|isdir)',a) for a in astr),
            'skip_or_xfail':bool(re.search(r'pytest\.(?:skip|xfail)',s))}

rows=[]
for d in sorted(ET.iterdir()):
    if not (d/'task.toml').exists(): continue
    desc=read(d/'instruction.md'); df=read(d/'environment/Dockerfile'); test=read(d/'tests/test_final_state.py'); ts=read(d/'tests/test.sh')
    try: meta=tomli.loads(read(d/'task.toml')).get('metadata',{})
    except Exception: meta={}
    feat=test_features(test)
    rates={}
    for model,key in [('o3','o3'),('meta-llama_Llama-3.2-3B-Instruct','llama3b')]:
        p=d/'solution'/(model+'_summary.json')
        if p.exists():
            j=json.loads(read(p)); rates[key]={'n':j.get('num_runs'),'s':j.get('num_success')}
    flags=[]
    if re.search(NETWORK,desc+'\n'+test,re.I): flags.append('runtime_network_text')
    if re.search(HEAVY,desc+'\n'+test,re.I): flags.append('service_or_heavy_text')
    if feat['syntax_error'] or feat['assertions']<2 or feat['test_functions']==0 or feat['presence_only'] or feat.get('skip_or_xfail'): flags.append('weak_verifier_static')
    if re.search(r'(?im)^\s*(?:COPY|ADD)\s+.*(?:task\.json|test_final|solution|truth)',df) or re.search(r'(?i)[./](?:\.?truth|answer|solution|expected)[\w.-]*\.(?:json|txt|csv|py)',df): flags.append('answer_file_suspect')
    if re.search(r'(?im)^\s*(?:COPY|ADD)\s+\.\s',df): flags.append('copy_entire_context')
    extra=set(feat['imports'])-set(sys.stdlib_module_names)-{'pytest','__future__',''}
    if extra: flags.append('nonstdlib_test_import')
    frm=re.findall(r'(?im)^FROM\s+(\S+)',df)
    if frm!=['ubuntu:22.04']: flags.append('other_base')
    if re.search(r'\b(?:at most|maximum(?: of)?|no more than|within|only)\s+(?:\*\*)?\d+[^\n]{0,30}(?:commands|command|steps)',desc,re.I): flags.append('command_count_constraint')
    rec={'id':d.name,'difficulty':meta.get('difficulty'),'category':meta.get('category'),'tags':meta.get('tags'), 'rates':rates,'base':frm,'topic':bool(re.search(TOPIC,desc,re.I)),'repair':bool(re.search(REPAIR,desc,re.I)), 'flags':flags,'extra_test_imports':sorted(extra),**feat,'instruction_hash':h(desc),'normalized_instruction_hash':h(norm(desc)),'test_hash':h(test),'normalized_test_hash':h(norm(test)), 'instruction':desc}
    rows.append(rec)
    
with (OUT/'endless_inventory.jsonl').open('w') as f:
    for row in rows: f.write(json.dumps(row)+'\n')
def counts(rs):
    return {'n':len(rs),'difficulty':dict(collections.Counter(r.get('difficulty') for r in rs)), 'flags':dict(collections.Counter(x for r in rs for x in r.get('flags',[]))), 'exact_instruction_groups':len(set(r['instruction_hash'] for r in rs)), 'normalized_instruction_groups':len(set(r['normalized_instruction_hash'] for r in rs)), 'normalized_test_groups':len(set(r['normalized_test_hash'] for r in rs)), 'o3_hist':dict(sorted(collections.Counter(r['rates']['o3']['s'] for r in rs if 'o3' in r['rates']).items())), 'llama3b_hist':dict(sorted(collections.Counter(r['rates']['llama3b']['s'] for r in rs if 'llama3b' in r['rates']).items())), 'paired_rates':sum('o3' in r['rates'] and 'llama3b' in r['rates'] for r in rs)}
strict_flags={'runtime_network_text','service_or_heavy_text','weak_verifier_static','answer_file_suspect','copy_entire_context','nonstdlib_test_import','other_base'}
local=[r for r in rows if not strict_flags.intersection(r['flags']) and r['topic']]
oracle=[r for r in local if r['rates'].get('o3',{}).get('s',0)>=12]
stats={'all':counts(rows),'local_text':counts(local),'local_text_o3_ge12':counts(oracle),'local_repair_o3_ge12':counts([r for r in oracle if r['repair']]), 'run_counts':dict(collections.Counter(v['n'] for r in rows for v in r['rates'].values()))}
(OUT/'endless_stats.json').write_text(json.dumps(stats,indent=2));print('ENDLESS',json.dumps(stats,indent=2))

tm=pq.read_table(OUT/'tmax_harbor.parquet').to_pylist()
canonical={r['task_id']:r for r in pq.read_table(OUT/'tmax_canonical_audit_columns.parquet').to_pylist()}
matched=0
for r in tm:
    key=r['task_id'].removeprefix('tmax/')
    if key in canonical:
        r['test_final_state']=canonical[key]['test_final_state']
        r['container_def']=canonical[key]['container_def']
        matched+=1
assert matched==len(tm), (matched,len(tm))
meta_counts={k:dict(collections.Counter(r[k] for r in tm)) for k in ['domain','task_complexity','command_complexity','language']}
trows=[]
for r in tm:
    desc=r['instruction'];test=r['test_final_state'];df=r['container_def'];feat=test_features(test)
    flags=[]
    if re.search(NETWORK,desc+'\n'+test,re.I):flags.append('runtime_network_text')
    if re.search(HEAVY,desc+'\n'+test,re.I):flags.append('service_or_heavy_text')
    if re.search(r'\b(?:image|screenshot|audio|video|png|jpeg|wav|mp4|ocr)\b',desc,re.I):flags.append('multimedia_text')
    if re.search(r'(?i)[./](?:\.?truth|answer|solution|expected)[\w.-]*\.(?:json|txt|csv|py)',df):flags.append('answer_file_suspect')
    if feat['syntax_error'] or feat['assertions']<2 or feat['test_functions']==0 or feat['presence_only'] or feat.get('skip_or_xfail'):flags.append('weak_verifier_static')
    extra=set(feat['imports'])-set(sys.stdlib_module_names)-{'pytest','__future__',''}
    if extra: flags.append('nonstdlib_test_import')
    r2={k:r[k] for k in ['task_id','domain','skill_type','primitive_skills','task_complexity','command_complexity','language','scenario']}
    r2.update({'flags':flags,**feat,'instruction_hash':h(desc),'normalized_instruction_hash':h(norm(desc)),'normalized_test_hash':h(norm(test)),'repair':bool(re.search(REPAIR,desc,re.I))})
    trows.append(r2)
basic=[r for r in trows if r['domain'] in ['debugging','data_processing'] and r['language'] in ['Python','Bash','Python 3','python','bash'] and r['task_complexity'].startswith(('short','moderate'))]
clean=[r for r in basic if not r['flags']]
def tc(rs): return {'n':len(rs),'flags':dict(collections.Counter(x for r in rs for x in r['flags'])),'complexity':dict(collections.Counter(r['task_complexity'] for r in rs)),'language':dict(collections.Counter(r['language'] for r in rs)),'repair':sum(r['repair'] for r in rs),'normalized_instruction_groups':len(set(r['normalized_instruction_hash'] for r in rs)),'normalized_test_groups':len(set(r['normalized_test_hash'] for r in rs))}
tstats={'metadata':meta_counts,'python_bash_nonintricate_debug_data':tc(basic),'static_clean_slice':tc(clean)}
(OUT/'tmax_stats.json').write_text(json.dumps(tstats,indent=2));print('TMAX',json.dumps(tstats,indent=2))
with (OUT/'tmax_inventory.jsonl').open('w') as f:
    for r in trows:f.write(json.dumps(r)+'\n')
(OUT/'tmax_static_candidate_ids.json').write_text(json.dumps([r['task_id'] for r in clean],indent=2))

se=pq.read_table(OUT/'seta.parquet').to_pylist()
def sroot(s):return re.sub(r'__(?:[a-z]\d+)$','',s)
sstat={'rows':len(se),'source_roots':len(set(sroot(r['task_id']) for r in se)),'difficulty':dict(collections.Counter(r['difficulty'] for r in se)),'subset':dict(collections.Counter(r['subset'] for r in se)),'source':dict(collections.Counter(r['source_corpus'] for r in se)), 'category':dict(collections.Counter(r['category'] for r in se))}
(OUT/'seta_stats.json').write_text(json.dumps(sstat,indent=2));print('SETA',json.dumps(sstat,indent=2))
