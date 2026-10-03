import asyncio
import copy
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app.sim import World
from app.allocation import allocate, move, reroute_onboard
from app.ledger import Ledger

SCENARIOS=('earthquake_surge','hospital_failure','supply_shortage')

class Simulation:
    def __init__(self,seed=7,name='earthquake_surge'):
        self.seed=seed; self.name=name; self.playing=False; self.speed=1
        self.smart=World(seed); self.smart.wave(14)
        self.baseline=copy.deepcopy(self.smart); self.ledger=Ledger(); self.changes=[]
        self.accounts={'donor':10000,'agency':0,'field':0,'vendor':0}
        for source,target,amount in [('donor','agency',6000),('agency','field',4000),('field','vendor',1500)]:
            self.transfer(source,target,amount,'FUND-001')
        self.dispatch('blood',20,'H1','BLOOD-001')
        self.reallocate()

    def transfer(self,source,target,amount,trace_id):
        self.accounts[source]-=amount; self.accounts[target]+=amount
        self.ledger.append(self.smart.tick,'fund_donation' if source=='donor' else 'fund_transfer',dict(trace_id=trace_id,source=source,target=target,amount=amount))

    def dispatch(self,resource,amount,hospital,trace_id):
        for w in (self.smart,self.baseline):
            w.supplies[resource]-=amount
            if resource=='blood': next(h for h in w.hospitals if h['id']==hospital)['blood']+=amount
        for kind,source,target in [('supply_dispatch','warehouse','field-unit'),('supply_receipt','field-unit',hospital)]:
            self.ledger.append(self.smart.tick,kind,dict(trace_id=trace_id,resource=resource,amount=amount,source=source,target=target))

    def reallocate(self,event=False):
        self.changes=[]
        for name,w in [('smart',self.smart),('baseline',self.baseline)]:
            before=len(w.decisions)
            if event: reroute_onboard(w,name=='smart')
            allocate(w,name=='smart',event)
            for d in w.decisions[before:]:
                self.ledger.append(w.tick,'allocation',dict(policy=name,**d))
                if name=='smart': self.changes.append(d)

    def event(self,kind,data):
        # Validate the entire operation before changing either policy.
        if kind in ('block','reopen') and not self.smart.graph.has_edge(data.get('u'),data.get('v')): raise ValueError('Unknown road')
        if kind=='hospital' and (data.get('hospital') not in [h['id'] for h in self.smart.hospitals] or data.get('status') not in ('full','offline','normal')): raise ValueError('Invalid hospital or status')
        if kind=='breakdown' and data.get('ambulance') not in [a['id'] for a in self.smart.ambulances]: raise ValueError('Unknown ambulance')
        if kind=='surge' and (type(data.get('count',10)) is not int or not 1<=data.get('count',10)<=50): raise ValueError('Surge count must be 1–50')
        if kind=='shortage' and data.get('resource','blood') not in ('blood','medicines'): raise ValueError('Unknown resource')
        if kind not in ('block','reopen','hospital','breakdown','surge','shortage'): raise ValueError('Unknown event')
        for w in (self.smart,self.baseline):
            if kind in ('block','reopen'):
                w.graph[data['u']][data['v']]['blocked']=kind=='block'; w.graph.graph.pop('routes',None)
            elif kind=='hospital':
                h=next(h for h in w.hospitals if h['id']==data['hospital']); h['forced']=None if data['status']=='normal' else data['status']; h['status']=data['status']
            elif kind=='surge': w.wave(data.get('count',10))
            elif kind=='shortage':
                resource=data.get('resource','blood'); w.supplies[resource]=0
                if resource=='blood':
                    for h in w.hospitals: h['blood']=0
            elif kind=='breakdown':
                a=next(a for a in w.ambulances if a['id']==data['ambulance'])
                if a['patient']:
                    p=next(p for p in w.patients if p['id']==a['patient']); p.update(node=a['node'],status='waiting',assignment=None)
                a.update(status='broken',patient=None,hospital=None,path=[],edge_left=0)
        self.ledger.append(self.smart.tick,'event',dict(event=kind,**data)); self.reallocate(True)

    def step(self,n):
        for _ in range(n):
            for w in (self.smart,self.baseline): move(w)
            t=self.smart.tick
            if t==4 and self.name=='earthquake_surge': self.event('surge',{'count':18})
            elif t==7 and self.name=='earthquake_surge':
                u,v=list(self.smart.graph.edges)[12]; self.event('block',{'u':u,'v':v})
            elif t==5 and self.name=='hospital_failure': self.event('hospital',{'hospital':'H1','status':'offline'})
            elif t==5 and self.name=='supply_shortage': self.event('shortage',{'resource':'blood'})
            elif t==6 and self.name=='supply_shortage': self.event('surge',{'count':12})
            elif t==12 and self.name=='supply_shortage':
                # A scripted free relief shipment arrives at two hospitals.
                for w in (self.smart,self.baseline): w.supplies['blood']+=24
                self.ledger.append(t,'supply_receipt',dict(trace_id='BLOOD-002',source='donor-depot',target='warehouse',resource='blood',amount=24))
                self.dispatch('blood',12,'H4','BLOOD-002'); self.dispatch('blood',12,'H5','BLOOD-002'); self.reallocate(True)
            else: self.reallocate()

    def state(self):
        worlds={}
        for name,w in [('smart',self.smart),('baseline',self.baseline)]:
            worlds[name]=dict(hospitals=w.hospitals,ambulances=w.ambulances,patients=w.patients,metrics=w.metrics(),supplies=w.supplies,
                assignments=[dict(patient=p['id'],**p['assignment']) for p in w.patients if p['assignment'] and p['status']!='delivered'])
        return dict(seed=self.seed,scenario=self.name,tick=self.smart.tick,playing=self.playing,speed=self.speed,
            graph=dict(nodes=[dict(id=n,**a) for n,a in self.smart.graph.nodes(data=True)],edges=[dict(u=u,v=v,**a) for u,v,a in self.smart.graph.edges(data=True)]),
            worlds=worlds,changes=self.changes,accounts=self.accounts)

sim=Simulation()

@asynccontextmanager
async def lifespan(app):
    async def autoplay():
        while True:
            await asyncio.sleep(1/sim.speed)
            if sim.playing: sim.step(1)
    task=asyncio.create_task(autoplay())
    yield
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass

app=FastAPI(title='Relief Lab • Offline prototype',lifespan=lifespan)

class Start(BaseModel):
    seed:int=Field(default=7,ge=0,le=2147483647)
    scenario:Literal['earthquake_surge','hospital_failure','supply_shortage']='earthquake_surge'
class Step(BaseModel):
    n:int=Field(default=1,ge=1,le=100)
class Play(BaseModel):
    enabled:bool
    speed:float=Field(default=1,ge=.25,le=5)

@app.get('/')
def page(): return FileResponse(Path(__file__).resolve().parent.parent/'static'/'index.html')
@app.post('/scenario/start')
async def start(body:Start):
    global sim
    sim=Simulation(body.seed,body.scenario); return sim.state()
@app.post('/scenario/step')
async def step(body:Step): sim.step(body.n); return sim.state()
@app.post('/scenario/autoplay')
async def autoplay(body:Play): sim.playing=body.enabled; sim.speed=body.speed; return sim.state()
@app.post('/events/{kind}')
async def event(kind:str,body:dict):
    try: sim.event(kind,body)
    except ValueError as e: raise HTTPException(400,str(e))
    return sim.state()
@app.get('/state')
async def state(): return sim.state()
@app.get('/decisions')
async def decisions(): return {'smart':sim.smart.decisions[-100:],'baseline':sim.baseline.decisions[-100:]}
@app.get('/ledger')
async def ledger(): return sim.ledger.blocks
@app.get('/ledger/verify')
async def verify(): return sim.ledger.verify()
@app.get('/ledger/trace/{identifier}')
async def trace(identifier:str): return sim.ledger.trace(identifier)
@app.post('/ledger/tamper/{block}')
async def tamper(block:int):
    if not 0<=block<len(sim.ledger.blocks): raise HTTPException(404,'Unknown block')
    sim.ledger.blocks[block]['payload']['tampered']=True; return sim.ledger.verify()
@app.post('/ledger/reset')
async def reset():
    global sim
    sim=Simulation(sim.seed,sim.name); return sim.state()
