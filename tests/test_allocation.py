from app.sim import World
from app.allocation import allocate, occupied, move

def test_capacity():
    w=World(); w.wave(80)
    for _ in range(50):
        allocate(w); move(w)
        for h in w.hospitals:
            assert occupied(w,h,True)<=h['icu']
            assert occupied(w,h,False)<=h['beds']

def test_event_reallocates():
    w=World(); w.wave(15); allocate(w)
    h=next(h for h in w.hospitals if any(p['assignment'] and p['assignment']['hospital']==h['id'] for p in w.patients))
    h['forced']='offline'; allocate(w,event=True)
    assert w.allocation_runs==2
    assert all(not p['assignment'] or p['assignment']['hospital']!=h['id'] for p in w.patients)
