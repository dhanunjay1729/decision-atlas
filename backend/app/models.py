from typing import Annotated, Literal
from pydantic import BaseModel, Field, model_validator

class Source(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=250)
    text: str = Field(min_length=1, max_length=30000)
    page: int | None = Field(default=None, ge=1, le=10000)
    kind: Literal['document', 'web', 'sample'] = 'document'
    url: str | None = None

class PrepareRequest(BaseModel):
    question: str = Field(min_length=5, max_length=800)
    sources: list[Source] = Field(default_factory=list, max_length=60)
    include_web: bool = False
    participant_count: int = Field(default=3, ge=2, le=5)

    @model_validator(mode='after')
    def check_sources(self):
        if len(self.question.strip()) < 5:
            raise ValueError('Please enter a complete question.')
        if sum(len(s.text) for s in self.sources) > 30000:
            raise ValueError('Combined source text exceeds 30,000 characters.')
        if any(s.kind != 'document' or s.url for s in self.sources):
            raise ValueError('Only document passages are accepted from the client.')
        if len({s.id for s in self.sources}) != len(self.sources):
            raise ValueError('Source IDs must be unique.')
        return self

class AnalyzeRequest(PrepareRequest):
    perspectives: list[str] = Field(min_length=2, max_length=5)

    @model_validator(mode='after')
    def check_roles(self):
        if any(not r.strip() or len(r) > 100 for r in self.perspectives):
            raise ValueError('Each perspective needs 1–100 characters.')
        normalized = [r.strip().casefold() for r in self.perspectives]
        if len(set(normalized)) != len(normalized):
            raise ValueError('Choose distinct perspectives.')
        return self

class PerspectiveOutput(BaseModel):
    perspectives: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(min_length=2, max_length=5)
    suggested_question: Annotated[str, Field(max_length=800)] | None

class DraftClaim(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    source_ids: list[str] = Field(max_length=5)
    kind: Literal['empirical', 'value'] = 'empirical'

class ArgumentOutput(BaseModel):
    position: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=2000)
    claims: list[DraftClaim] = Field(min_length=1, max_length=2)
    challenges: list[str] = Field(max_length=8)

class Claim(BaseModel):
    id: str
    agent: int
    text: str
    status: Literal['supported', 'contradicted', 'insufficient', 'value', 'unverified', 'review'] = 'insufficient'
    source_ids: list[str]
    explanation: str = 'Verification pending.'
    assessments: list[dict] = Field(default_factory=list)
    kind: Literal['empirical', 'value'] = 'empirical'

class Argument(BaseModel):
    agent: int
    round: int
    position: str
    body: str
    claim_ids: list[str]
    challenges: list[str]
    model: str | None = None

class Assessment(BaseModel):
    claim_id: str
    status: Literal['supported', 'contradicted', 'insufficient', 'value']
    source_ids: list[str] = Field(max_length=5)
    explanation: str = Field(min_length=1, max_length=1000)

class VerificationOutput(BaseModel):
    assessments: list[Assessment] = Field(max_length=24)

class ReportOutput(BaseModel):
    report: str = Field(min_length=100, max_length=10000)

class ReportSections(BaseModel):
    perspectives: str = Field(min_length=1,max_length=1200)
    evidence: str = Field(min_length=1,max_length=1200)
    tradeoffs: str = Field(min_length=1,max_length=1200)
    revisions: str = Field(min_length=1,max_length=1200)
    gaps: str = Field(min_length=1,max_length=1200)
    priorities: str = Field(min_length=1,max_length=1200)
