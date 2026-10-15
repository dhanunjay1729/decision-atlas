import asyncio,json
import pytest
from app.engine import apply_kinds,apply_verification,debate
from app.models import Claim,ClaimKindsOutput,ReportReviewOutput,ReportOutput,ReportSections,ArgumentOutput,AnalyzeRequest,VerificationOutput

def test_empirical_effect_cannot_be_accepted_as_a_value():
    claims=[Claim(id='c1',agent=0,text='Group assignments develop communication skills.',kind='value',source_ids=[])]
    apply_kinds(claims,ClaimKindsOutput(classifications=[{'claim_id':'c1','kind':'empirical'}]),False)
    assert claims[0].status=='unverified'
    output=VerificationOutput(assessments=[dict(claim_id='c1',status='value',explanation='A teaching preference.',source_ids=[])])
    apply_verification(claims,[],output)
    assert claims[0].status=='insufficient'

def test_classification_rejects_missing_or_duplicate_ids():
    claim=Claim(id='c1',agent=0,text='Fairness should matter.',source_ids=[])
    with pytest.raises(ValueError):apply_kinds([claim],ClaimKindsOutput(classifications=[]),False)
    with pytest.raises(ValueError):apply_kinds([claim],ClaimKindsOutput(classifications=[dict(claim_id='c1',kind='value')]*2),False)

class AuditedProvider:
    def __init__(self,persistent_failure=False):self.reviews=0;self.reports=0;self.persistent_failure=persistent_failure
    def for_stage(self,*args):return self
    async def generate(self,system,prompt,schema):
        data=json.loads(prompt)
        if schema is ArgumentOutput:return schema(position='Priorities differ',body='A comparison of priorities.',claims=[dict(text='Fairness should matter.',kind='value',source_ids=[])],challenges=[])
        if schema is ClaimKindsOutput:return schema(classifications=[dict(claim_id=c['id'],kind='value') for c in data['claims']])
        if schema is ReportReviewOutput:
            self.reviews+=1;bad=self.reviews==1 or self.persistent_failure
            return schema(acceptable=not bad,issues=['Do not recommend a hybrid compromise.'] if bad else [])
        assert schema is ReportOutput
        self.reports+=1
        if self.reports>1:assert data['review_issues']==['Do not recommend a hybrid compromise.']
        return schema(report=' '.join(['Different priorities remain unresolved and factual effects have not been independently verified.']*30))

def test_failed_report_review_gets_one_bounded_rewrite():
    provider=AuditedProvider()
    async def run():return [e async for e in debate(AnalyzeRequest(question='Which approach should we choose?',perspectives=['A','B']),[],provider)]
    result=asyncio.run(run())
    assert result[-1]['type']=='complete'
    assert provider.reports==provider.reviews==2

def test_persistent_report_review_failure_never_claims_completion():
    provider=AuditedProvider(True);events=[]
    async def run():
        async for event in debate(AnalyzeRequest(question='Which approach should we choose?',perspectives=['A','B']),[],provider):events.append(event)
    with pytest.raises(ValueError,match='balance'):asyncio.run(run())
    assert provider.reports==2
    assert not any(e['type']=='complete' for e in events)

def test_observed_adoption_advice_is_rejected_but_open_questions_are_allowed():
    from app.engine import report_advice_issues
    assert report_advice_issues('Evidence is uncertain. Untested contexts warrant cautious, monitored adoption rather than blanket endorsement.')
    assert report_advice_issues('Until evidence is available, a reasonable approach may be to combine formats.')
    assert not report_advice_issues('What level of evidence would justify adoption? How should autonomy and learning outcomes be weighed?')

def test_audit_rewrite_restores_word_range_without_rerunning_arguments():
    class ShortRewrite(AuditedProvider):
        def __init__(self):super().__init__();self.arguments=0;self.sections=0
        async def generate(self,system,prompt,schema):
            if schema is ArgumentOutput:self.arguments+=1
            if schema is ReportOutput and self.reports==1:
                self.reports+=1
                return ReportOutput(report=' '.join(['Some priorities remain unresolved.']*35))
            if schema is ReportSections:
                self.sections+=1
                return schema(**{k:' '.join(['Open questions remain about evidence, implementation, and competing priorities.']*6) for k in schema.model_fields})
            return await super().generate(system,prompt,schema)
    provider=ShortRewrite()
    async def run():return [e async for e in debate(AnalyzeRequest(question='Which approach should we choose?',perspectives=['A','B']),[],provider)]
    result=asyncio.run(run())
    assert result[-1]['type']=='complete' and provider.sections==1
    assert provider.arguments==4
    assert 300<=len(result[-1]['analysis']['report'].split())<=500
