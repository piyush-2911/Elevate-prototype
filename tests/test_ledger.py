from app.ledger import Ledger

def test_tamper():
    ledger=Ledger(); ledger.append(0,'donation',{'trace_id':'F1','amount':20})
    ledger.append(1,'transfer',{'trace_id':'F1','amount':10})
    assert ledger.verify()['valid']; assert len(ledger.trace('F1'))==2
    ledger.blocks[0]['payload']['amount']=999
    assert ledger.verify()['first_invalid_block']==0
