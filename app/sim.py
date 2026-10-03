"""Small deterministic synthetic city. One tick is one simulated minute."""
import random
import networkx as nx


def road_graph(seed):
    rng = random.Random(seed)
    g = nx.Graph()
    for i in range(49):
        g.add_node(i, x=60+(i%7)*90, y=60+(i//7)*75)
    for i in range(49):
        for j in (i+1 if i%7<6 else -1, i+7):
            if 0 <= j < 49:
                g.add_edge(i, j, time=rng.randint(1, 3), blocked=False)
    for u, v in list(g.edges):
        if rng.random() < .08:
            attrs = dict(g[u][v]); g.remove_edge(u,v)
            if not nx.is_connected(g): g.add_edge(u,v,**attrs)
    for u,v in [(0,16),(12,32),(24,40)]:
        g.add_edge(u,v,time=3,blocked=False)
    return g


def route(g, source, target):
    live = nx.subgraph_view(g, filter_edge=lambda u,v: not g[u][v]['blocked'])
    try:
        path = nx.shortest_path(live, source, target, weight='time')
        return sum(g[u][v]['time'] for u,v in zip(path,path[1:])), path
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return float('inf'), []


class World:
    def __init__(self, seed=7):
        self.seed=seed; self.rng=random.Random(seed); self.tick=0
        self.graph=road_graph(seed); self.patients=[]; self.decisions=[]
        self.hospitals=[dict(id=f'H{i+1}', node=n, specialty=s, icu=3, beds=8,
            used_icu=0, used_beds=0, blood=12, status='normal', forced=None)
            for i,(n,s) in enumerate([(0,'trauma'),(6,'burn'),(24,'general'),(42,'trauma'),(48,'burn')])]
        self.ambulances=[dict(id=f'A{i+1}', node=n, type='ALS' if i<6 else 'BLS',
            status='idle', patient=None, hospital=None, path=[], edge_left=0)
            for i,n in enumerate([0,6,24,42,48,16,8,20,30,40])]
        self.supplies={'blood':100,'medicines':200}; self.reallocations=0
        self.busy_ticks=0; self.peak_load=0; self.allocation_runs=0

    def wave(self, count=8):
        for _ in range(count):
            severity=self.rng.choices([1,2,3,4],[4,3,2,1])[0]
            self.patients.append(dict(id=f'P{len(self.patients)+1}', node=self.rng.randrange(49),
                severity=severity, need=self.rng.choice(['trauma','burn','general']),
                icu=severity==1, born=self.tick, deadline=self.tick+[0,18,28,40,55][severity],
                status='waiting', reason='Awaiting allocation', arrived=None, assignment=None))

    def metrics(self):
        arrivals=[p['arrived']-p['born'] for p in self.patients if p['arrived'] is not None]
        return dict(average_time_to_hospital=round(sum(arrivals)/len(arrivals),2) if arrivals else None,
            delivered=len(arrivals), past_deadline=sum((p['arrived'] if p['arrived'] is not None else self.tick)>p['deadline'] for p in self.patients),
            hospital_peak_load=round(self.peak_load,3), reallocations=self.reallocations,
            ambulance_utilization=round(self.busy_ticks/max(1,self.tick*len(self.ambulances)),3))
