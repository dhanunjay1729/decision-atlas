"""Firestore ledger for Cloud Run; no container-local state is used.

The client and transaction runner are injectable for offline behavior tests.
Actual SDK transaction integration must also be checked against Firestore before publishing.
"""
import hashlib,ipaddress,os,re,secrets,time,uuid
from .budget import LimitError,utc_budget_day

class FirestoreLedger:
    def __init__(self,client=None,runner=None,collection="decision_atlas"):
        if not re.fullmatch(r"[a-zA-Z0-9_]{1,80}",collection):raise ValueError("Invalid ledger collection.")
        if client is None:
            from google.cloud import firestore
            client=firestore.Client(database='(default)')
            runner=lambda callback:firestore.transactional(callback)(client.transaction())
        self.client=client
        self.runner=runner
        if runner is None:raise ValueError('A transaction runner is required for an injected client.')
        self.collection=client.collection(collection)
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
        if maximum_cost < 0:raise ValueError('Reservation must not be negative.')
        now=time.time();day,_,_,_=utc_budget_day(now)
        daily_ref=self.collection.document('daily_'+day)
        key=uuid.uuid4().hex
        reservation=self.collection.document('reservation_'+key)
        def write(tx):
            state=self._read(self.state,tx)
            daily=self._read(daily_ref,tx).get('total',0.0)
            total=state['total']+maximum_cost
            if total>float(os.getenv('TOTAL_MODEL_BUDGET_USD','2')):
                raise LimitError('The demo model budget has been reached. The saved sample is still available.')
            if daily+maximum_cost>float(os.getenv('DAILY_MODEL_BUDGET_USD','1')):
                raise LimitError('Today’s debate allowance has been reached. Live debates resume at 00:00 UTC; featured debates remain available.')
            tx.update(self.state,{'total':total})
            tx.set(daily_ref,{'total':daily+maximum_cost})
            tx.set(reservation,{'amount':maximum_cost,'created':now,'day':day})
            return key
        return self._run(write)

    def settle(self,reservation,actual_cost):
        if actual_cost < 0:raise ValueError('Actual cost must not be negative.')
        ref=self.collection.document('reservation_'+reservation)
        def write(tx):
            state=self._read(self.state,tx);entry=self._read(ref,tx)
            reserved=entry['amount']
            day=entry.get('day') or utc_budget_day(entry['created'])[0]
            daily_ref=self.collection.document('daily_'+day)
            daily=self._read(daily_ref,tx)
            tx.update(self.state,{'total':state['total']-reserved+actual_cost})
            # Old reservations were never added to daily totals; add their actual charge once.
            difference=actual_cost-reserved if entry.get('day') else actual_cost
            tx.set(daily_ref,{'total':daily.get('total',0.0)+difference})
            tx.update(ref,{'amount':actual_cost,'day':day})
            return actual_cost>reserved+1e-9
        exceeded=self._run(write)
        if exceeded:raise LimitError('Provider usage exceeded the configured estimate; stop and review model pricing.')

    def daily_status(self):
        day,_,_,resets_at=utc_budget_day()
        ref=self.collection.document('daily_'+day)
        spent=self._run(lambda tx:self._read(ref,tx).get('total',0.0))
        return {'available':spent<float(os.getenv('DAILY_MODEL_BUDGET_USD','1')),'resets_at':resets_at}

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
