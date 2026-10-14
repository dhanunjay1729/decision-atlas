import asyncio
import json
import pytest
from pydantic import ValidationError
from app.engine import debate
from app.models import AnalyzeRequest, ArgumentOutput, ReportOutput, VerificationOutput

class KnowledgeProvider:
    def __init__(self): self.prompts=[]
    async def generate(self,system,prompt,schema):
        data=json.loads(prompt);self.prompts.append(data)
        assert schema is not VerificationOutput, 'No source-free fact verification'
        if schema is ArgumentOutput:
            return schema(position='Consider trade-offs',body='This uses general knowledge, not independently verified sources.',claims=[{'text':'An unsourced factual assertion.','source_ids':['invented']},{'text':'Fairness should matter.','source_ids':[],'kind':'value'}],challenges=['c1'] if data['round']==2 else [])
        return ReportOutput(report=' '.join(['These assertions remain unverified and the priorities involve value judgments.']*35))

@pytest.mark.parametrize('count',[2,3,4,5])
def test_optional_evidence_and_dynamic_round_snapshots(count):
    request=AnalyzeRequest(question='Which approach is preferable?',perspectives=[f'Role {i}' for i in range(count)])
    provider=KnowledgeProvider()
    async def run():return [e async for e in debate(request,[],provider)]
    result=asyncio.run(run())[-1]['analysis']
    assert len(result['arguments'])==2*count
    assert all(p['previous_round_arguments']==[] for p in provider.prompts[:count])
    assert all(len(p['previous_round_arguments'])==count for p in provider.prompts[count:count*2])
    assert result['evidence_mode']=='knowledge'
    assert all(c['source_ids']==[] for c in result['claims'])
    assert {c['status'] for c in result['claims']}=={'unverified','value'}

@pytest.mark.parametrize('roles',[['One'],['x']*6,['Same',' same ']])
def test_out_of_range_or_duplicate_roles_rejected(roles):
    with pytest.raises(ValidationError):AnalyzeRequest(question='Which approach is preferable?',perspectives=roles)
