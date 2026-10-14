# Decision Atlas

An evidence-grounded multi-agent debate workspace with configurable Gemini integration.

## What works now

- React/TypeScript interface with editable questions and three perspectives.
- Local PDF text extraction (5 MB and 30 pages per file; combined evidence text 30,000 characters).
- Optional pasted text and document/web selection.
- Clearly labeled, hand-authored attendance-policy sample, played through two visible rounds.
- Claim inspection, source passages, interactive React Flow graph, balanced report, Markdown export.
- FastAPI backend with document chunking and BM25-style retrieval, two-round orchestration, structured verification, and report validation.
- Gemini integration: Flash-Lite currently handles perspective preparation, arguments, verification, and reports; stages remain separately configurable.
- Configurable Gemini-direct and OpenAI-compatible adapters; secrets stay in an ignored local `.env`.
- Structured schemas, paced requests, and explicit quota/service errors without paid fallbacks.
- SQLite request limits and conservative model-cost reservations.

## What is not connected yet

Gemini has been selected and live structured-output probes have been run. Web retrieval is intentionally unavailable; selecting it returns an explicit error rather than fabricated sources. The published static preview includes the interface and sample, but does not host Python. The FastAPI backend can serve the built interface together with its API on a separate Python host. Deployment of the complete live backend, source-quality checks, model-specific tuning, and the human-reviewed evaluation remain future work.

The sample sources are fictional illustrative passages, not real research. Its labels are hand-authored, not measured verification results. Live document-backed analysis accepts arbitrary questions when Gemini is configured; the sample is tied to its displayed attendance question.

## Run locally

```bash
npm ci --cache /tmp/decision-atlas-npm-cache
npm run build
python -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. For frontend development, run `npm run dev`; Vite proxies `/api` to FastAPI on port 8000.

## Gemini configuration

Copy `.env.example` to `.env` and enter the key locally, or set environment variables on the server. FastAPI automatically loads the project-root `.env` without overriding server environment variables. The key is never sent to the browser or committed to Git.

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

Backend tests exercise round isolation, retrieval, source-reference validation, budget persistence, rejected client web sources, and unconfigured/live-service behavior. Gemini endpoints have been probed with small structured-output tasks. This is functional testing, not an accuracy benchmark. No general model accuracy or baseline improvement is claimed.

## Current free-tier model selection

- `gemini-3.5-flash-lite`: all current stages, including arguments, evidence verification, and the final report.
- The preparation model remains separately configurable through `MODEL_PREPARE_NAME`.
- `gemini-3.8-flash` returned HTTP 503 on two live probes. `gemini-3.6-flash` passed a small probe but returned a service error when starting a full debate. Neither is used as an automatic fallback. Flash-Lite was selected for availability and low latency; this is not a universal reasoning-quality ranking.

Official references: [models](https://ai.google.dev/gemini-api/docs/models), [free-tier pricing](https://ai.google.dev/gemini-api/docs/pricing), [structured outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output), and [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits). Actual account quotas must be checked in AI Studio. A complete analysis normally uses nine model calls: one preparation call and eight debate/verification/report calls. One extra report correction is allowed if its length is outside 300–500 words. Free-tier capacity is not a promise of 100 runs in a day.

`GEMINI_FREE_TIER_ONLY=true` restricts the application to an explicit list of models that have documented free inference tiers, requires zero configured inference prices, and disallows switching to another provider. It does **not** change Google's project billing tier. Keep the Google project on the free tier; enabling billing can incur provider charges even if this app's local accounting prices are zero. There are no automatic paid fallbacks, search grounding, or repeated quota retries.

The default low thinking level and 6,000-token output ceiling give the verifier room for all extracted claims. Request starts are paced six seconds apart by default; adjust this to your actual account quota. A quota failure remains visible and stops the run. Uploaded documents are sent to Google's API during live analysis; Google's free-tier data policy applies.

## Local project location

The working checkout is `/home/dhanunjay1729/decision-atlas`. Start it with `bash run_local.sh`. The virtual environment is ignored and can be recreated using the commands above.

## Live integration check — 14 October 2026

A complete live run using Gemini 3.5 Flash-Lite finished in approximately 52 seconds. It generated three short perspective labels, six arguments across two rounds, twelve claim assessments with validated source IDs, and a 391-word balanced report. The source was an explicitly fictional attendance-policy document used for integration testing. No genuine study, factual accuracy percentage, or superiority over a single-agent baseline is claimed. Human-reviewed verification accuracy and real-source retrieval remain pending.

The integration revealed and fixed excessive perspective-label lengths, output-token limits, and out-of-range report length. Tests cover free-tier model restrictions, sanitized quota/access/service errors, missing and truncated responses, a single bounded report correction, and the streaming API completion contract. The application's selected model and local API key are configured in `.env`; that file is mode 600 and ignored by Git.
