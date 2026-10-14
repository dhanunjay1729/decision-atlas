# Decision Atlas

A multi-perspective debate workspace for comparing arguments, evidence and priorities.

## User flow

1. Enter a debatable question. Documents and pasted text are optional.
2. Turn **Search the web** on when current evidence is wanted. Off uses model knowledge and any documents supplied.
3. Ask AI to suggest 2–5 viewpoints, or write your own. Edit, add and remove roles; the user chooses the final participants.
4. Review the estimated cost, then explicitly start the debate.
5. Follow two rounds: opening perspectives, then specific challenges and retained or revised positions. Inspect claims, sources and the graph; read or export a balanced 300–500 word report with no winner or policy recommendation.

Unsourced factual claims are labeled **model knowledge—unverified**. Source-backed claims are assessed against selected passages. Haiku and GPT-OSS 20B cross-check the assessments; disagreements receive **requires review**, with both explanations visible. Agreement does not establish universal truth or source quality.

## Model and retrieval behavior

The server pins the inexpensive models and providers in `backend/app/gateway.py`:

- Perspective suggestions: Qwen 3.7 Flash via Alibaba.
- Web-off drafts: Qwen 3.8 27B via RunInfra. On temporary capacity/rate-limit failures, one bounded fallback uses Haiku 5.5 via Anthropic; RunInfra is cooled down for two minutes. Actual draft models are displayed.
- Web-on drafts: two or more Qwen 3.7 Flash perspectives with one Haiku perspective, depending on the user-selected 2–5 participant count.
- Source-backed verification: Haiku plus GPT-OSS 20B via DeepInfra.
- Report writing: Haiku, with bounded length correction and a six-section fallback.

No arbitrary or expensive model/provider fallbacks are enabled. All participants in a round see the same fixed previous-round snapshot. Statements, documents, roles and previous arguments are treated as untrusted content rather than instructions.

Web mode uses exactly one shared Perplexity Search through the Vercel AI Gateway SDK. Raw result excerpts and original URLs are retained, not invented from a model summary. Retrieval selects up to five representative passages totaling at most 6,500 characters. When documents and web results are both present, both kinds remain represented. These are partial excerpts, not exhaustive readings of the sources.

## Run locally

Requires Python 3.12+ and Node.js 22+ (the search helper uses the AI SDK).

```bash
npm ci
npm run build
python -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cp .env.example .env
# Enter AI_GATEWAY_API_KEY privately in .env.
bash run_local.sh
```

The checkout is `/home/dhanunjay1729/decision-atlas`. FastAPI serves the built frontend and API together. Default URL: http://127.0.0.1:8000. If that port is occupied, use `DECISION_ATLAS_PORT=8003 bash run_local.sh`. The current reviewed preview uses http://127.0.0.1:8003.

For frontend development, `npm run dev` proxies `/api` to port 8000; change the Vite proxy if using another backend port.

## Configuration and costs

Use server environment variables or a mode-600, ignored `.env`. Never put credentials in `VITE_` variables, tracked files, browser storage or client requests. FastAPI loads `.env` without overriding existing server variables. `/api/status` exposes readiness and a model-pool label, never credentials.

`TOTAL_MODEL_BUDGET_USD=2` is a persistent application cap; it is separate from the earlier $0.50 research allowance. Cost estimates target an average of $0.02 per debate ($2 per 100). This is a planning target, not a promise that 100 arbitrary five-person debates will succeed. Context, search, report corrections and provider failures affect charges. Before each paid call the SQLite ledger reserves a conservative upper bound and settles returned usage. Unknown failures retain their reservation. The report displays tracked cost, which can include retained reservations. A depleted budget stops further calls.

There are no recurring purchases or automatic credit top-ups. Provider-side pricing changes require reviewing the fixed rate assumptions. Conservative reservations are application safeguards, not a provider billing guarantee.

Use a persistent volume for `LEDGER_PATH`. Runs are serialized within one Python process; multiple workers/replicas require shared concurrency control. Preparation and analysis each count toward rate limits. Public deployment should enforce request-body limits and configure trusted proxy IPs. A no-login public demo needs controlled access and monitoring before enabling paid traffic.

Each network IP receives five lifetime debate starts (`MAX_DEBATES_PER_IP=5`). A start consumes a use even if a model later fails; suggestions and cost previews do not consume this allowance. The counter is checked atomically before paid debate work and survives restarts. Only salted IP hashes are recorded for new counters. Shared Wi-Fi shares the allowance, and changing networks can bypass it; this is a demo safeguard, not user identity or hardware tracking. Configure the ASGI trusted-proxy allowlist correctly when hosting, and retain the SQLite volume.

## APIs

- `GET /api/allowance`: used and remaining debate starts for this network.
- `GET /api/status`: readiness and provider-pool label.
- `POST /api/prepare`: `{question, participant_count}`; returns suggested viewpoints and an optional neutral question. Neither is automatically used as a final choice.
- `POST /api/estimate`: `{question, perspectives, sources, include_web}`; deterministic planning estimate, no model/search charge.
- `POST /api/analyze`: same setup; streams progress, selected sources, arguments, completion or explicit errors via SSE.

Client evidence must be document text; clients cannot supply trusted web sources or arbitrary model IDs. The server does not fetch user-supplied URLs. PDFs are parsed locally (5 MB / 30 pages each; combined text limit 30,000 characters); scanned PDFs require pasted text.

Legacy Gemini-direct and generic OpenAI-compatible adapters remain available for development. They do not provide the pinned gateway pool or shared web-search integration.

## Validation

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
npm run build
```

Tests cover 2–5 participants, equal round snapshots, source-free unverified labels, forged client sources, persistent spending limits, provider pinning, bounded cheap fallback, verification disagreement, single shared search, bounded verification batches, atomic five-start IP allowances and document/web coexistence. The hand-authored attendance sample uses fictional passages; its labels are illustrative.

Live checks of the connected gateway are functional checks, not accuracy benchmarks. A real web run completed with six arguments, four source excerpts and a 425-word report, with tracked cost about $0.00953. A five-debater document run completed with ten arguments and a 358-word report at $0.01156 tracked cost, including the bounded Haiku fallback. A source-free check exposed a RunInfra quota failure and motivated the bounded Haiku fallback. Five-topic model simulations informed the pool; general accuracy, third-round benefit and improvement over a single-agent baseline are not claimed. The human claim/evidence review and deployment remain separate review steps.

## Deployment

A Dockerfile is included (the image build has not yet been verified) for a single-process Python + Node deployment. Mount persistent storage at `/app/work`, supply `AI_GATEWAY_API_KEY` securely, and set `LEDGER_PATH=/app/work/usage.sqlite3`. The image never copies local credentials or research artifacts. Publication should follow review of live outputs; the current deliverable is the local app and GitHub source.
