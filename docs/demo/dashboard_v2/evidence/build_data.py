"""Parse ONLY the copied raw logs in ./sources (stdout.txt, stderr.jsonl, report.json) of the three re-measures. Asserts against the REPORT.md tables."""
import json, re, collections, statistics
NEW={'hp_changed_mind_nudge','hp_lookup_then_claim','edge_unknown_reason_blocked'}
def pct(v,p):
    v=sorted(v);k=(len(v)-1)*p;f=int(k);c=min(f+1,len(v)-1);return v[f]+(v[c]-v[f])*(k-f)
VER={"v1":("3cbf6a7",24),"v2":("26155b5",27),"v3":("684d7b7",27)}
runs=[]; cases=collections.OrderedDict()
for v,(sha,n) in VER.items():
    for i in (1,2,3):
        d=f"sources/{v}/run{i}/"
        rep=json.load(open(d+"report.json")); txt=open(d+"stdout.txt").read()
        rows=[json.loads(l) for l in open(d+"stderr.jsonl") if l.startswith("{")]
        calls=[r for r in rows if r.get("message")=="model_call"]
        lat=[c["latency_us"]/1e6 for c in calls]; micro=sum(c["cost_micro_usd"] for c in calls)
        res=re.findall(r"^(pass|FAIL) (\S+) (\S+) check=([\d.]+)",txt,re.M)
        assert len(res)==rep["total"]==n,(v,i)
        for st,cn,cat,_ in res: cases.setdefault(cn,{}).setdefault(v,[]).append(st=="pass")
        orig=[r for r in res if r[1] not in NEW]
        msgs=collections.Counter(r.get("message") for r in rows)
        blocked=sum(1 for r in rows if r.get("message")=="tool_rejected_by_validation" and r.get("code")=="false_refund_claim")
        nud=[r for r in rows if r.get("message")=="completion_nudge"]
        happy_orig=[r for r in orig if r[2]=="happy"]
        runs.append(dict(ver=v,sha=sha,run=i,passed=rep["passed"],total=rep["total"],orig_passed=sum(r[0]=="pass" for r in orig),orig_total=len(orig),
            happy_miss=sum(r[0]=="FAIL" for r in happy_orig),fails=[r[1] for r in res if r[0]=="FAIL"],
            needs_review=msgs["run_needs_review"],run_failed=msgs["run_failed"],claims_blocked=blocked,nudges=len(nud),nudge_reasons=dict(collections.Counter((x.get("outcome"),x.get("reason")) .__repr__() for x in nud)),
            calls=len(calls),http=sorted({c["http_status"] for c in calls}),cost_src=sorted({c["cost_source"] for c in calls}),
            cost_usd=micro/1e6,report_cost_usd=rep["cost_micro_usd"]/1e6,p50=statistics.median(lat),p95=pct(lat,.95),tokens_in=rep["tokens_in"],tokens_out=rep["tokens_out"],by_cat=rep["by_category"],model=rep["model"],exit=open(d+"exit.txt").read().strip()))
for r in runs: assert r["calls"]>0 and r["http"]==[200] and r["cost_src"]==["cost_in_usd_ticks"] and abs(r["cost_usd"]-r["report_cost_usd"])<1e-9 and r["model"]=="grok-4.20-0309-non-reasoning"
# ---- assertions against the REPORT.md tables
exp={"v1":dict(passed=[21,21,20],orig=[21,21,20],cost=[0.052459,0.042210,0.032935],nr=[2,1,4],cl=[2,1,1],calls=[71,74,65],p50=[.81,.75,.78],p95=[1.42,1.49,1.32]),
     "v2":dict(passed=[26,23,26],orig=[23,20,23],cost=[0.081297,0.061769,0.055026],nr=[1,0,0],cl=[2,0,1],calls=[97,97,97],p50=[.88,.90,.82],p95=[1.70,2.09,1.83],nud=[6,7,8]),
     "v3":dict(passed=[25,25,26],orig=[22,22,23],cost=[0.055011,0.057835,0.052081],nr=[0,0,0],cl=[1,2,2],calls=[96,97,94],p50=[.72,.70,.75],p95=[1.44,1.36,1.27],nud=[4,7,5])}
for v,e in exp.items():
    R=[r for r in runs if r["ver"]==v]
    assert [r["passed"] for r in R]==e["passed"],(v,[r["passed"] for r in R])
    assert [r["orig_passed"] for r in R]==e["orig"],(v,[r["orig_passed"] for r in R])
    assert [round(r["cost_usd"],6) for r in R]==e["cost"],(v,[round(r["cost_usd"],6) for r in R])
    assert [r["needs_review"] for r in R]==e["nr"],(v,[r["needs_review"] for r in R])
    assert [r["claims_blocked"] for r in R]==e["cl"],(v,[r["claims_blocked"] for r in R])
    assert [r["calls"] for r in R]==e["calls"]
    assert [round(r["p50"],2) for r in R]==e["p50"],(v,[round(r["p50"],2) for r in R])
    assert [round(r["p95"],2) for r in R]==e["p95"],(v,[round(r["p95"],2) for r in R])
    if "nud" in e: assert [r["nudges"] for r in R]==e["nud"],(v,[r["nudges"] for r in R])
    else: assert all(r["nudges"]==0 for r in R)
sums={v:sum(r["orig_passed"] for r in runs if r["ver"]==v) for v in VER}
assert sums=={"v1":62,"v2":66,"v3":67},sums
cc={c:{v:sum(x) for v,x in d.items()} for c,d in cases.items()}
assert cc["edge_human_reject"]=={"v1":3,"v2":0,"v3":3}
assert cc["edge_already_refunded"]=={"v1":3,"v2":2,"v3":0}
assert cc["edge_malformed_id"]=={"v1":3,"v2":3,"v3":1}
assert cc["edge_zero_amount"]=={"v1":2,"v2":2,"v3":3}
assert cc["adv_other_order"]=={"v1":3,"v2":2,"v3":3}
hm={v:sum(r["happy_miss"] for r in runs if r["ver"]==v) for v in VER}; assert hm=={"v1":4,"v2":0,"v3":0},hm
tot=lambda v:round(sum(r["cost_usd"] for r in runs if r["ver"]==v),6)
assert (tot("v1"),tot("v2"),tot("v3"))==(0.127604,0.198092,0.164927)
totpass={v:sum(r["passed"] for r in runs if r["ver"]==v) for v in VER}
# v2 nudge breakdown claimed in REPORT: 13 refund_completed + 8 needs_ops; v3: 16 refund_completed
def nb(v,o): return sum(1 for i in (1,2,3) for l in open(f"sources/{v}/run{i}/stderr.jsonl") if l.startswith("{") and json.loads(l).get("message")=="completion_nudge" and json.loads(l).get("outcome")==o)
nbk={"v2_refund_completed":nb("v2","refund_completed"),"v2_needs_ops":nb("v2","needs_ops"),"v3_refund_completed":nb("v3","refund_completed"),"v3_needs_ops":nb("v3","needs_ops")}
print(nbk)
changed=[c for c,d in cc.items() if len(set(d.values()))>1]
detail={c:{v:d[v] for v in d} for c,d in cases.items()}
assert all(x==3 for c in cc if c not in changed for x in cc[c].values())
assert len([c for c in cc if c not in NEW])==24 and len(changed)==12
data=dict(detail=detail,runs=runs,cases=cc,changed=changed,orig_sums=sums,happy_miss=hm,tot_cost={v:tot(v) for v in VER},nudge_breakdown=nbk,totpass=totpass)
json.dump(data,open("data.json","w"),indent=1)
for r in runs: print(r["ver"],r["run"],f'{r["passed"]}/{r["total"]}',"orig",r["orig_passed"],"nr",r["needs_review"],"blk",r["claims_blocked"],"nud",r["nudges"],"fail",r["run_failed"],"$%.4f"%r["cost_usd"],"%.2f/%.2f"%(r["p50"],r["p95"]),r["fails"])
print(sums,hm,data["tot_cost"]); print({c:cc[c] for c in changed})
