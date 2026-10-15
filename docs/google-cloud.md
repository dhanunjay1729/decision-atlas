# Google Cloud deployment: private validation first

Status: publicly deployed at [Decision Atlas](https://decision-atlas-358533498865.us-central1.run.app/). CLI authentication, Docker build/runtime, real Firestore transactions and all three hosted evidence modes were validated. This guide retains the private-first setup procedure for reproducibility.

## What the user supplies

1. Sign into [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a dedicated project named Decision Atlas and share its **Project ID**, not credentials.
3. Check whether billing is a Free Trial or Paid account. Complete any account/identity/payment setup personally. Do not activate an upgrade assuming it guarantees a free bill.

The selected proposal is Cloud Run (app) plus Firestore Standard, Native mode, `(default)` database (persistent budget and network counters). No Cloud SQL, GPU, VM, load balancer, or custom domain is needed. Existing local usage is not automatically migrated to Firestore: use a separate explicitly chosen deployment budget, or seed the cloud ledger with prior usage before enabling live access. Do not silently reset an existing cloud ledger, collection, or IP salt on redeploy.

## Cost envelope

Use request-based billing, zero minimum instances, one maximum instance, one CPU, 512 MiB memory, a 600-second request timeout, and concurrency two. The app serializes expensive work per process; Firestore atomically reserves the global budget across revisions/instances. Cloud Run may temporarily exceed its configured instance maximum, so that setting alone is not a spending cap.

Free allowances and availability must be checked against the billing account and region. Cloud Run request-based pricing currently includes 180,000 vCPU-seconds, 360,000 GiB-seconds and two million requests monthly, based on us-central1 pricing. Firestore's default database has free daily reads/writes and storage allowances. Builds, image storage, secrets, logging and internet traffic have separate pricing/allowances. The application's $2 cap covers model/search reservations only, not Google Cloud infrastructure.

Configure billing notifications, and inspect spend-cap support for the services in this project. Alerts-only budgets do not stop charges. Enable registry cleanup only after reviewing which image versions must be retained; keep image storage within its free allowance where possible.

References checked 2026-10-15: [Cloud Run pricing](https://cloud.google.com/run/pricing), [Firestore pricing](https://cloud.google.com/firestore/pricing), [Free program](https://docs.cloud.google.com/free/docs/free-cloud-features), [Billing controls](https://docs.cloud.google.com/billing/docs/how-to/budgets), [Maximum instances](https://docs.cloud.google.com/run/docs/configuring/max-instances-limits).

## Provisioning after the project is selected

Use an authenticated local gcloud CLI or the project's Cloud Shell. Review commands using the actual project ID before running them.

- Enable Cloud Run, Firestore, Artifact Registry, Cloud Build and Secret Manager APIs as needed for the chosen build path.
- Create or reuse the `(default)` Firestore **Standard / Native** database. Confirm region before creation; do not create an extra named database expecting another free allowance.
- Create a dedicated runtime service account. In this dedicated project grant Firestore access with `roles/datastore.user`. Grant `roles/secretmanager.secretAccessor` only on the specific gateway secret, rather than project-wide secret access. Do not create or download service-account JSON keys: Cloud Run uses its attached runtime identity.
- Put the gateway key in Secret Manager privately. Pin the deployment to the reviewed secret version. Never put keys in commands, Git, cloud build context or chat.
- Build and push the reviewed Docker image to a single Artifact Registry repository. `.gcloudignore` and `.dockerignore` exclude `.env`, research output and credentials from uploads/images. The build context must be the project root.

## Reviewed private deployment

`scripts/deploy_gcp.py` prints the command by default. Example placeholders must be replaced with real reviewed values:

```bash
python scripts/deploy_gcp.py \
  --project YOUR_PROJECT_ID \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/decision-atlas/app@sha256:YOUR_DIGEST \
  --service-account decision-atlas-runtime@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

Add `--apply` only when the required resources, runtime identity, image and secret exist and the command has been reviewed. It deploys **private**, requiring IAM authentication. It does not provision resources or grant public access.

## Validation before publication

1. Confirm the container starts, the static frontend loads, `node --version` works, and model readiness is reported without exposing secrets. The cloud app refuses to use ephemeral SQLite when `K_SERVICE` is set.
2. Confirm live SDK transactions work against the intended Firestore project: reserve, settle, block an over-budget reservation, persist a counter across a new client/container, and atomically reject a sixth start. Use an isolated test collection/project rather than deleting production records.
3. Verify the ingress proxy chain. Uvicorn proxy parsing is disabled in the image. `TRUSTED_PROXY_HOPS=0` initially uses the socket peer, so private preview may share one allowance. Before public use, configure `TRUSTED_PROXY_CIDRS` to the verified immediate ingress peers and `TRUSTED_PROXY_HOPS` to the correct client position counted from the right. Never trust the first arbitrary forwarded IP or a guessed proxy count. Test spoofed header prefixes and multiple actual client networks. This step is required for a meaningful per-IP public allowance.
4. Check SSE progress, disconnected clients, report length and neutrality, source coverage, body limit (256 KB), depleted allowance and spending cap. Paid checks count against the agreed model budget.
5. Restart/update the private service and confirm counters and reservations persist. Confirm old and new revisions use the same Firestore state.
6. Only after these checks, grant public invocation and verify the resulting URL. No public IAM change has been made by the preparation script.

Official guides: [Deploy containers](https://docs.cloud.google.com/run/docs/deploying), [Runtime identity](https://docs.cloud.google.com/run/docs/securing/service-identity), [Secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets), [Firestore server client](https://docs.cloud.google.com/firestore/native/docs/create-database-server-client-library).

## Current deployment record

- Project: `decision-atlas` (`358533498865`); app and default Standard/Native Firestore database in `us-central1`. Firestore reported `freeTier: true` at creation.
- Runtime identity: `decision-atlas-runtime@decision-atlas.iam.gserviceaccount.com`. Firestore data access on this dedicated project; access to only the `atlas-gateway` secret, version 1. No service-account key file was created.
- Public invocation is enabled on the Cloud Run service only. Unauthenticated direct Firestore reads returned 403. The disabled deployment diagnostic route returns 404.
- Request-based CPU allocation, 1 CPU, 512 MiB, minimum zero / maximum one instance, concurrency two, 600-second request timeout. Google Cloud infrastructure remains metered; the $2 app cap covers model/search costs, not all cloud services.
- On this direct Cloud Run ingress, the observed socket peer was within `169.254.0.0/16`; Google appended one actual client address to the forwarded chain. Normal and forged-prefix requests had the same rightmost client address. Current settings: `TRUSTED_PROXY_HOPS=1`, `TRUSTED_PROXY_CIDRS=169.254.0.0/16`, Uvicorn proxy parsing off. Revalidate before adding a load balancer/proxy or changing ingress architecture. Do not reuse these values blindly on another host.
- The private three-mode suite and suggestions used $0.020553 tracked model cost. The private socket-peer test allowance was filled to five without additional model calls; the next HTTP analysis returned 429 with an unchanged cost total. After switching to client-IP identity, the tested client had all five starts available. Previous spending records remained in Firestore across revisions.
- Hosted smoke outputs: knowledge 316 words / 4 arguments; fictional document 321 words / 10 arguments; web 328 words / 6 arguments / 4 source excerpts. No general accuracy superiority is claimed.
- Public browser checks covered model readiness, the free cost preview, 2–5 participant controls and a 375-pixel mobile layout without horizontal overflow.

For routine image updates, use `gcloud run services update decision-atlas --image=REVIEWED_DIGEST --region=us-central1 --project=decision-atlas` to preserve the verified environment and runtime identity. The preparation script intentionally defaults to a private preview and zero trusted proxy hops, so re-running it is not the production update procedure. Retain the same Firestore collection, budget document and salt; do not reset them to deploy.

Current reviewed release image: `us-central1-docker.pkg.dev/decision-atlas/decision-atlas/app@sha256:b110f4de41945901a6996987e88bbff089c4c1e6ed299d8167cd0b75c48a5f2c`.


## Owner access, daily usage, and community storage

The current release uses `DAILY_MODEL_BUDGET_USD=1` plus the existing `TOTAL_MODEL_BUDGET_USD=2`. Every inference/search reservation checks the UTC-day document and lifetime budget in a Firestore transaction. Failed calls retain reservations; settlements update the original reservation day. The daily reset is 00:00 UTC (05:30 India time). The site and public gallery remain online when new AI work is paused. These settings do not limit the GCP infrastructure bill.

Owner privileges now derive from a Firebase-verified Google login: the token must have a verified email matching `OWNER_GOOGLE_EMAIL`, and its `firebase.sign_in_provider` must be `google.com`. Password login with the same address does not qualify. The backend verifies signature, issuer/audience, expiry and account revocation; ownership is never inferred from a browser-supplied email. There is no owner-token form or cookie fallback. Owners bypass visitor quotas but not server spending controls. Existing IP counters remain intact.

Optional publication saves sanitized private snapshots in 500 bounded slots. Publication capabilities expire after 24 hours; expired slots are overwritten on reuse. Only explicit consent exposes a completed snapshot in Featured debates. Public copies contain generated prose and source metadata, not source passages, costs, keys, publication tokens, or voter hashes. Users must review their generated prose for private information. The gallery retains at most 200 posts (including hidden posts); a normalized salted-IP hash limits each network to one like per post. Ranking combines likes and recency, not evidence quality. The owner can hide a post to remove public access without permanently deleting its snapshot.

Offline tests and a real Firestore SDK check validate the new quota/gallery transactions in an isolated collection; see `evaluation/community-cloud-checks.json`. No model calls are needed for these checks.

The daily-cap rollout migrated 137 existing reservations for 2026-10-15 into that day’s accounting ($0.086111), marking their reservation day while preserving lifetime totals, IP salt, and start counters. The owner and daily-cap release passed 82 offline tests plus the isolated real Firestore checks.

## Managed accounts and private history

Email/password signup and login use Google Identity Platform (Firebase Authentication). The deployed configuration enables email-enumeration protection, authorizes the Cloud Run domain, and enforces an eight-character minimum password. Public client configuration is provided through `/api/auth/config` using `FIREBASE_PROJECT_ID`, `FIREBASE_WEB_API_KEY`, and `FIREBASE_AUTH_DOMAIN`. This client key identifies the authentication project; it is not the AI Gateway credential.

The runtime identity has `roles/firebaseauth.viewer` for Firebase Admin token revocation/disabled-account checks. The browser sends ID tokens, not passwords, to FastAPI. History routes derive ownership from verified token claims and never accept a browser-supplied user ID. Firestore account-history documents are accessed through the server identity; the frontend does not directly access Firestore.

Signed-in completed runs are saved privately with selected source passages and claim assessments. The store uses a separate namespace, salted account identifiers, and bounded allocations of 100 retained snapshots per account and 1,000 globally. Hidden snapshots remain private and count toward retention limits. A history save failure is reported alongside the completed result rather than discarding paid work. Guest runs are not attached retroactively.

The release passed 115 offline tests and a real managed-auth/Firestore check in an isolated collection (`evaluation/accounts-cloud-checks.json`). Signup and password login were verified with disposable synthetic accounts, without model calls. Signup does not bypass visitor usage limits; owner access remains separate.


Google sign-in requires enabling the Google provider in Firebase Authentication and configuring its web OAuth client. `FIREBASE_GOOGLE_ENABLED=true` exposes the Google button once that setup is complete. Support email and OAuth client setup are handled through the project’s authenticated Firebase console. The former `atlas-owner` secret is no longer used by the application.

Google provider setup is enabled and its web client is configured. Release `decision-atlas-00007-6sp` serves the Google-owner/account-history image above. The public login page was checked for the Google button, optional guest use, and removal of the former owner form.
