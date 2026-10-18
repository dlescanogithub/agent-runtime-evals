import json,re,statistics,sys,glob
out=[]
tot_ticks=0
def pct(v,p):
    v=sorted(v); k=(len(v)-1)*p; f=int(k); c=min(f+1,len(v)-1); return v[f]+(v[c]-v[f])*(k-f)
for n in (1,2,3):
    d=f'run{n}'
    rep=json.load(open(f'{d}/report.json'))
    rows=[json.loads(l) for l in open(f'{d}/stderr.jsonl') if l.startswith('{')]
    calls=[r for r in rows if r.get('message')=='model_call']
    lat=[c['latency_us']/1e6 for c in calls]
    micro=sum(c['cost_micro_usd'] for c in calls)
    srcs={c.get('cost_source') for c in calls}
    st={c.get('http_status') for c in calls}
    txt=open(f'{d}/stdout.txt').read()
    fails=re.findall(r'^FAIL (\S+) (\S+)',txt,re.M)
    fclaim=len(re.findall(r'false_refund_claim',txt))
    nr=len(re.findall(r'needs_review',txt))
    msgs=__import__('collections').Counter(r.get('message') for r in rows)
    blocked=[r for r in rows if 'false_refund_claim' in json.dumps(r)]
    print(f"run{n}: {rep['passed']}/{rep['total']} {rep['by_category']} calls={len(calls)} http={st} src={srcs} cost_calls=${micro/1e6:.6f} report=${rep['cost_micro_usd']/1e6:.6f} p50={statistics.median(lat):.3f}s p95={pct(lat,.95):.3f}s tokens={rep['tokens_in']}/{rep['tokens_out']}")
    print('  FAIL:',fails,' false_refund_claim lines in stdout:',fclaim,' needs_review lines:',nr, ' false-claim log rows:',len(blocked))
    for l in txt.splitlines():
        if l.startswith('FAIL') or l.startswith('  '): pass
    print('  msgs:',dict(msgs))
    tot_ticks+=micro
print('total $',tot_ticks/1e6)
