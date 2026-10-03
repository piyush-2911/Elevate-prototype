"""Global ambulance matching, followed by capacity-safe hospital reservations."""
import numpy as np
from scipy.optimize import linear_sum_assignment
from app.sim import route

BIG=1e8

def occupied(w,h,icu):
    return h['used_icu' if icu else 'used_beds']+sum(
        p['status'] in ('assigned','transporting') and p['assignment'] and
        p['assignment']['hospital']==h['id'] and p['icu']==icu for p in w.patients)

def choices(w,a,p,smart):
    if p['severity']==1 and a['type']!='ALS': return []
    pickup,first=route(w.graph,a['node'],p['node'])
    if not first: return []
    options=[]
    for h in w.hospitals:
        capacity=h['icu' if p['icu'] else 'beds']; load=occupied(w,h,p['icu'])
        blood_reserved=sum(q['status'] in ('assigned','transporting') and q['assignment'] and q['assignment']['hospital']==h['id'] and q['severity']<=2 for q in w.patients)
        if h['forced'] in ('offline','full') or load>=capacity: continue
        if p['severity']<=2 and h['blood']<=blood_reserved: continue
        if p['need']!='general' and h['specialty']!=p['need']: continue
        travel,path=route(w.graph,p['node'],h['node'])
        if not path: continue
        total=pickup+travel; slack=p['deadline']-w.tick-total
        cost=(total+4*load/capacity+max(0,-slack)*8-35*(5-p['severity'])
              -2*(w.tick-p['born'])+(3 if a['type']=='ALS' and p['severity']>1 else 0)) if smart else travel
        options.append((cost,total,h,first+path[1:],pickup))
    return sorted(options,key=lambda x:(x[0],x[2]['id']))

def allocate(w,smart=True,event=False):
    w.allocation_runs+=1
    old={p['id']:dict(p['assignment']) for p in w.patients if p['assignment'] and p['status']=='assigned'}
    # At event boundaries, release uncollected patients; onboard patients stay onboard.
    if event:
        for a in w.ambulances:
            if a['status']=='en-route':
                p=next(p for p in w.patients if p['id']==a['patient'])
                p.update(status='waiting',assignment=None)
                a.update(status='idle',patient=None,hospital=None,path=[],edge_left=0)
    waiting=[p for p in w.patients if p['status']=='waiting']
    idle=[a for a in w.ambulances if a['status']=='idle']
    for p in waiting: p['reason']='No compatible ambulance, reachable hospital, bed or blood available'
    if not waiting or not idle: return
    if smart:
        costs=np.full((len(idle),len(waiting)+len(idle)),BIG)
        for i,a in enumerate(idle):
            for j,p in enumerate(waiting):
                opts=choices(w,a,p,True)
                if opts: costs[i,j]=opts[0][0]
        costs[:,len(waiting):]=10000
        rows,cols=linear_sum_assignment(costs)
        pairs=[(idle[i],waiting[j]) for i,j in zip(rows,cols) if j<len(waiting) and costs[i,j]<BIG]
        pairs.sort(key=lambda pair:(pair[1]['severity'],pair[1]['deadline'],pair[1]['id']))
    else:
        pairs=[]; remaining=list(idle)
        for p in waiting:
            feasible=[a for a in remaining if choices(w,a,p,False)]
            if feasible:
                a=min(feasible,key=lambda a:route(w.graph,a['node'],p['node'])[0]); remaining.remove(a); pairs.append((a,p))
    for a,p in pairs:
        opts=choices(w,a,p,smart)
        if not opts: continue
        cost,total,h,path,pickup=opts[0]
        assignment={'ambulance':a['id'],'hospital':h['id']}
        changed=p['id'] in old and old[p['id']]!=assignment
        w.reallocations+=int(changed)
        p.update(status='assigned',assignment=assignment,reason='')
        a.update(status='en-route',patient=p['id'],hospital=h['id'],path=path,edge_left=0)
        explanation=f"{a['id']} → {p['id']} → {h['id']}: severity {p['severity']}, {total} min route, deadline in {p['deadline']-w.tick} min; {h['specialty']} match, projected bed load {occupied(w,h,p['icu'])}/{h['icu' if p['icu'] else 'beds']}. Blocked roads excluded; cost {cost:.1f}."
        w.decisions.append(dict(tick=w.tick,patient=p['id'],changed=changed,explanation=explanation,**assignment))

def move(w):
    w.tick+=1
    for p in w.patients:
        if p['status']=='waiting' and (w.tick-p['born'])%10==0:
            p['severity']=max(1,p['severity']-1); p['icu']=p['severity']==1
    for a in w.ambulances:
        if a['status'] not in ('en-route','transporting'): continue
        w.busy_ticks+=1
        p=next(p for p in w.patients if p['id']==a['patient'])
        h=next(h for h in w.hospitals if h['id']==a['hospital'])
        if a['node']==p['node'] and a['status']=='en-route':
            a['status']='transporting'; p['status']='transporting'
        if len(a['path'])>1:
            u,v=a['path'][:2]
            if w.graph[u][v]['blocked']: a['path']=[]; continue
            if not a['edge_left']: a['edge_left']=w.graph[u][v]['time']
            a['edge_left']-=1
            if not a['edge_left']: a['node']=v; a['path'].pop(0)
        if a['node']==p['node'] and a['status']=='en-route':
            a['status']='transporting'; p['status']='transporting'
        if p['assignment'] and a['node']==h['node'] and a['status']=='transporting' and h['forced'] not in ('offline','full'):
            h['used_icu' if p['icu'] else 'used_beds']+=1
            if p['severity']<=2: h['blood']-=1
            p.update(status='delivered',arrived=w.tick)
            a.update(status='idle',patient=None,hospital=None,path=[],edge_left=0)
    for h in w.hospitals:
        load=max(occupied(w,h,True)/h['icu'],occupied(w,h,False)/h['beds'])
        w.peak_load=max(w.peak_load,load)
        h['status']=h['forced'] or ('full' if load>=1 else 'near-capacity' if load>=.75 else 'normal')

def reroute_onboard(w,smart):
    for a in w.ambulances:
        if a['status']!='transporting': continue
        p=next(p for p in w.patients if p['id']==a['patient'])
        previous=a['hospital']; p['assignment']=None; p['node']=a['node']
        opts=choices(w,a,p,smart)
        if opts:
            _,_,h,path,_=opts[0]; a.update(hospital=h['id'],path=path,edge_left=0)
            p['assignment']={'ambulance':a['id'],'hospital':h['id']}
            if previous!=h['id']: w.reallocations+=1
            w.decisions.append(dict(tick=w.tick,patient=p['id'],ambulance=a['id'],hospital=h['id'],changed=previous!=h['id'],explanation=f"{a['id']} onboard {p['id']}: rerouted from {previous} to {h['id']} after event; current capacity, blood and open roads checked."))
        else:
            a.update(path=[],edge_left=0); p['reason']='Onboard: no feasible hospital; waiting for recovery event'
