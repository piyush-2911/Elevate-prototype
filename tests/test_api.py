from fastapi.testclient import TestClient
from app.api import app

def test_api_scenario_and_ledger():
    with TestClient(app) as c:
        a=c.post('/scenario/start',json={'seed':7}).json()
        b=c.post('/scenario/start',json={'seed':7}).json()
        assert a==b
        assert c.post('/events/hospital',json={'hospital':'H1','status':'offline'}).status_code==200
        assert c.post('/scenario/step',json={'n':20}).json()['tick']==20
        assert c.get('/ledger/verify').json()['valid']
        assert not c.post('/ledger/tamper/0').json()['valid']
        c.post('/ledger/reset'); assert c.get('/ledger/verify').json()['valid']
        assert len(c.get('/ledger/trace/FUND-001').json())==3
        assert c.post('/events/block',json={'u':-1,'v':100}).status_code==400
