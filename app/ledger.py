"""Demo hash chain, deterministic simulated timestamps, no personal data."""
import hashlib
import json
from datetime import datetime, timedelta, timezone


class Ledger:
    def __init__(self): self.blocks=[]

    @staticmethod
    def digest(block):
        content={k:v for k,v in block.items() if k!='hash'}
        return hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def append(self,tick,entry_type,payload):
        block=dict(index=len(self.blocks),previous_hash=self.blocks[-1]['hash'] if self.blocks else '0'*64,
            timestamp=(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(minutes=tick)).isoformat(),
            tick=tick,entry_type=entry_type,payload=payload)
        block['hash']=self.digest(block); self.blocks.append(block)
        return block

    def verify(self):
        previous='0'*64
        for i,b in enumerate(self.blocks):
            if b['index']!=i or b['previous_hash']!=previous or b['hash']!=self.digest(b):
                return {'valid':False,'first_invalid_block':i,'blocks':len(self.blocks)}
            previous=b['hash']
        return {'valid':True,'first_invalid_block':None,'blocks':len(self.blocks)}

    def trace(self,identifier):
        return [b for b in self.blocks if b['payload'].get('trace_id')==identifier]
