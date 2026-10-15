# Google Cloud deployment: private validation first

Status: deployment preparation, not a published service. Google Cloud authentication and the target project are not connected on this workstation. The Docker image and real Firestore SDK integration must pass validation before publishing. Unit tests exercise ledger behavior with a transactional fake; they do not prove live Firestore integration.

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
