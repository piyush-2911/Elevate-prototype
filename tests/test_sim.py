from app.sim import World, route

def test_blocked_route():
    w=World(); u,v=next(iter(w.graph.edges)); w.graph[u][v]['blocked']=True
    _,path=route(w.graph,u,v)
    assert all({a,b}!={u,v} for a,b in zip(path,path[1:]))

def test_seed():
    a,b=World(9),World(9); a.wave(); b.wave()
    assert a.patients==b.patients
    assert list(a.graph.edges(data=True))==list(b.graph.edges(data=True))
