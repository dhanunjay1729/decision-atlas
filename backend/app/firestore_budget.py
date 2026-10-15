"""Firestore ledger for Cloud Run; no container-local state is used.

The client and transaction runner are injectable for offline behavior tests.
Actual SDK transaction integration must also be checked against Firestore before publishing.
"""
import hashlib,ipaddress,os,secrets,time,uuid
from .budget import LimitError

class FirestoreLedger:
    def __init__(self,client=None,runner=None):
        if client is None:
            from google.cloud import firestore
            client=firestore.Client(database='(default)')
            runner=lambda callback:firestore.transactional(callback)(client.transaction())
        self.client=client
        self.runner=runner
        if runner is None:raise ValueError('A transaction runner is required for an injected client.')
        self.collection=client.collection('decision_atlas')
        self.state=self.collection.document('budget')
        def initialize(tx):
            data=self._read(self.state,tx)
            if not data:
                data={'total':0.0,'ip_salt':secrets.token_hex(32)}
                tx.set(self.state,data)
            return data['ip_salt']
        self.salt=self._run(initialize)

    def _run(self,callback):
        try:return self.runner(callback)
        except LimitError:raise
        except Exception:
            # Never continue paid work after a failed persistent counter operation.
            raise LimitError('The persistent budget store is unavailable. No further model calls can start.') from None

    @staticmethod
    def _read(ref,tx=None):
        return ref.get(transaction=tx).to_dict() or {}

    def ip_key(self,ip):
        try:
            address=ipaddress.ip_address(ip)
            ip=str(getattr(address,'ipv4_mapped',None) or address)
        except ValueError:pass
        return hashlib.sha256((self.salt+ip).encode()).hexdigest()

    def reserve(self,maximum_cost):
        key=uuid.uuid4().hex
        reservation=self.collection.document('reservation_'+key)
        def write(tx):
            state=self._read(self.state,tx)
            total=state['total']+maximum_cost
            if total>float(os.getenv('TOTAL_MODEL_BUDGET_USD','2')):
                raise LimitError('The demo model budget has been reached. The saved sample is still available.')
            tx.update(self.state,{'total':total})
            tx.set(reservation,{'amount':maximum_cost,'created':time.time()})
            return key
        return self._run(write)

    def settle(self,reservation,actual_cost):
        ref=self.collection.document('reservation_'+reservation)
        def write(tx):
            state=self._read(self.state,tx);entry=self._read(ref,tx)
            reserved=entry['amount']
            tx.update(self.state,{'total':state['total']-reserved+actual_cost})
            tx.update(ref,{'amount':actual_cost})
            return actual_cost>reserved+1e-9
        exceeded=self._run(write)
        if exceeded:raise LimitError('Provider usage exceeded the configured estimate; stop and review model pricing.')

    def total(self):
        return self._run(lambda tx:self._read(self.state,tx)['total'])

    def allowance(self,ip):
        ref=self.collection.document('network_'+self.ip_key(ip));limit=int(os.getenv('MAX_DEBATES_PER_IP','5'))
        used=self._run(lambda tx:self._read(ref,tx).get('used',0))
        return {'limit':limit,'used':used,'remaining':max(0,limit-used)}

    def start_debate(self,ip):
        ref=self.collection.document('network_'+self.ip_key(ip));limit=int(os.getenv('MAX_DEBATES_PER_IP','5'))
        def write(tx):
            used=self._read(ref,tx).get('used',0)
            if used>=limit:raise LimitError('This network has used its five-debate allowance. The saved sample remains available.')
            tx.set(ref,{'used':used+1},merge=True)
        self._run(write)

    def request(self,ip):
        global_ref=self.collection.document('request_limits')
        network_ref=self.collection.document('network_'+self.ip_key(ip));now=time.time()
        def write(tx):
            global_data=self._read(global_ref,tx);network_data=self._read(network_ref,tx)
            day=[t for t in global_data.get('timestamps',[]) if t>now-86400]
            hour=[t for t in network_data.get('timestamps',[]) if t>now-3600]
            if len(day)>=int(os.getenv('MAX_RUNS_PER_DAY','100')) or len(hour)>=int(os.getenv('MAX_RUNS_PER_IP_PER_HOUR','10')):
                raise LimitError('Live request limit reached. Please try the saved sample.')
            tx.set(global_ref,{'timestamps':day+[now]})
            tx.set(network_ref,{'timestamps':hour+[now]},merge=True)
        self._run(write)
