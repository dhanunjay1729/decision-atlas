# Decision Atlas

A model-independent first build of an evidence-grounded multi-agent debate workspace.

## What works now

- React/TypeScript interface with editable questions and three perspectives.
- Local PDF text extraction (5 MB and 30 pages per file; combined evidence text 30,000 characters).
- Optional pasted text and document/web selection.
- Clearly labeled, hand-authored attendance-policy sample, played through two visible rounds.
- Claim inspection, source passages, interactive React Flow graph, balanced report, Markdown export.
- FastAPI backend with document chunking and BM25-style retrieval, two-round orchestration, structured verification, and report validation.
- Configurable Gemini-direct and OpenAI-compatible model adapters; no default model or API key.
- SQLite request limits and conservative model-cost reservations.

## What is not connected yet

No live provider has been selected or tested. Web retrieval is intentionally unavailable; selecting it returns an explicit error rather than fabricated sources. The published static preview includes the interface and sample, but does not host Python. The FastAPI backend can serve the built interface together with its API on a separate Python host. Deployment of the complete live backend, source-quality checks, model-specific tuning, and the human-reviewed evaluation remain future work.

The sample sources are fictional illustrative passages, not real research. Its labels are hand-authored, not measured verification results. The app accepts arbitrary questions only once a live provider is configured; the sample is tied to its displayed attendance question.

## Run locally

```bash
npm ci --cache /tmp/decision-atlas-npm-cache
npm run build
python -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. For frontend development, run `npm run dev`; Vite proxies `/api` to FastAPI on port 8000.

## Select a model later

Set the environment variables shown in `.env.example` in the server environment. The example file is documentation; it is not automatically loaded. Alternatively, use Uvicorn's `--env-file` after adding its optional `python-dotenv` dependency.

- `MODEL_PROVIDER=gemini` for the Google direct adapter, or `openai_compatible` for a compatible endpoint.
- Set `MODEL_NAME` and `MODEL_API_KEY`.
- For compatible endpoints, set `MODEL_BASE_URL` to the HTTPS API base, such as one ending in `/v1`.
- Set both per-million input/output prices. Zero is accepted for genuinely free endpoints.
- Review output-token limits and provider schema support. Not all compatible providers support strict JSON schema.
- Keep secrets server-side; never use a `VITE_` variable for an API key.

`/api/status` reveals readiness and the model name, never the API key. A configured status is not proof that the selected provider passes our tests.

## API

`POST /api/prepare` proposes three topic-specific perspectives and an optional neutral framing. The user can edit the perspectives and must explicitly accept a suggested question.

`POST /api/analyze` accepts `{question, perspectives, sources, include_web}` and streams progress, argument, completion, or error events through SSE. Live document analysis requires `include_web=false` for this increment. Incoming evidence is document text; the API does not fetch user-supplied URLs.

Each round uses a fixed snapshot of the previous round. All agents in the same round see the same prior messages. Factual support labels require valid source IDs; incomplete or duplicate verification output is rejected. Matching a source ID does not establish semantic accuracy: human evaluation is still required.

## Budget and deployment notes

The default model allowance is $3, leaving room within the discussed $5 total for other services. Reservations use configured prices and conservative token bounds; errors retain the reservation because providers may bill failed requests. These are application controls, not a provider billing guarantee. Configure provider-side spending controls too. Search costs are not included yet.

The current request counters include perspective preparation and analysis separately. Configure persistent storage for the ledger on the eventual Python host; an ephemeral database would reset limits. Configure trusted proxy IPs explicitly. The current backend serializes runs in one process; multi-worker deployment needs shared concurrency control. Public-live hosting should add a maximum request-body size before enabling model traffic. PDF parsing currently happens in the browser; scanned documents need pasted text.

## Verification

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
npm run build
```

Backend tests exercise round isolation, retrieval, source-reference validation, budget persistence, rejected client web sources, and unconfigured/live-service behavior. Provider adapters have not been tested against real model endpoints. No model accuracy or baseline improvement is claimed.
