import pytest
from app.api import Simulation, SCENARIOS
from app.allocation import occupied

@pytest.mark.parametrize('name',SCENARIOS)
def test_demo_replay_and_capacity(name):
    a,b=Simulation(7,name),Simulation(7,name)
    for _ in range(40):
        a.step(1); b.step(1)
        for w in (a.smart,a.baseline):
            for h in w.hospitals:
                assert occupied(w,h,True)<=h['icu']
                assert occupied(w,h,False)<=h['beds']
                assert h['blood']>=0
    assert a.state()==b.state()
    assert a.ledger.blocks==b.ledger.blocks
    assert a.ledger.verify()['valid']
    assert a.smart.metrics()['past_deadline']<a.baseline.metrics()['past_deadline']

def test_event_routes_and_breakdown():
    s=Simulation(); s.step(2)
    a=next(a for a in s.smart.ambulances if len(a['path'])>1)
    u,v=a['path'][:2]; s.event('block',{'u':u,'v':v})
    for w in (s.smart,s.baseline):
        for ambulance in w.ambulances:
            assert all({x,y}!={u,v} for x,y in zip(ambulance['path'],ambulance['path'][1:]))
    s.event('reopen',{'u':u,'v':v}); assert not s.smart.graph[u][v]['blocked']
    s.event('breakdown',{'ambulance':'A1'})
    assert s.smart.ambulances[0]['status']=='broken'
    assert all(not p['assignment'] or p['assignment']['ambulance']!='A1' for p in s.smart.patients if p['status']!='delivered')

def test_funds_conserved_and_supply_trace():
    s=Simulation()
    assert sum(s.accounts.values())==10000
    assert [b['entry_type'] for b in s.ledger.trace('BLOOD-001')]==['supply_dispatch','supply_receipt']
