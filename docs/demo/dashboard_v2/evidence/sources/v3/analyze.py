import json,re,statistics,collections
NEW={'hp_changed_mind_nudge','hp_lookup_then_claim','edge_unknown_reason_blocked'}
def pct(v,p):
    v=sorted(v);k=(len(v)-1)*p;f=int(k);c=min(f+1,len(v)-1);return v[f]+(v[c]-v[f])*(k-f)
tot=0
for n in (1,2,3):
    d=f'run{n}'
    rep=json.load(open(f'{d}/report.json'))
    rows=[json.loads(l) for l in open(f'{d}/stderr.jsonl') if l.startswith('{')]
    calls=[r for r in rows if r.get('message')=='model_call']
    lat=[c['latency_us']/1e6 for c in calls]
    micro=sum(c['cost_micro_usd'] for c in calls); tot+=micro
    txt=open(f'{d}/stdout.txt').read()
    res=re.findall(r'^(pass|FAIL) (\S+) (\S+) check=([\d.]+)',txt,re.M)
    orig=[r for r in res if r[1] not in NEW]; new=[r for r in res if r[1] in NEW]
    po=sum(r[0]=='pass' for r in orig); pn=sum(r[0]=='pass' for r in new)
    msgs=collections.Counter(r.get('message') for r in rows)
    codes=collections.Counter((r.get('code'),r.get('tool')) for r in rows if r.get('message')=='tool_rejected_by_validation')
    print(f"run{n}: {rep['passed']}/{rep['total']} orig24={po}/{len(orig)} new3={pn}/{len(new)} cat={ {k:(v['passed'],v['total']) for k,v in rep['by_category'].items()} }")
    print(f"  calls={len(calls)} http={collections.Counter(c['http_status'] for c in calls)} src={ {c['cost_source'] for c in calls} } cost=${micro/1e6:.6f} report=${rep['cost_micro_usd']/1e6:.6f} p50={statistics.median(lat):.3f} p95={pct(lat,.95):.3f} tokens={rep['tokens_in']}/{rep['tokens_out']} nudges(report)={rep.get('completion_nudges')}")
    print('  fails:',[(r[1]) for r in res if r[0]=='FAIL'], ' new3:',[(r[1],r[0]) for r in new])
    print('  events:',{k:v for k,v in msgs.items() if k in('run_needs_review','run_failed','completion_nudge','gate_rejected','nudge','run_completed')}, 'rejected:',dict(codes))
    print('  msgs all:',dict(msgs))
print('total',tot/1e6)
