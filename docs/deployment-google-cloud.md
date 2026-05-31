# Google Cloud Deployment

Shinkai 1.0 is deployable as two Cloud Run services:

- `shinkai-api`: FastAPI backend, public read endpoints, admin-token-protected mutations.
- `shinkai-web`: Next.js dashboard, ordinary users can view results, admins can operate runs.

## GitHub Actions Setup

The deployment workflow uses Google Workload Identity Federation, not long-lived service account
keys. Configure these GitHub repository variables:

- `GCP_PROJECT_ID`: Google Cloud project ID.
- `GCP_REGION`: Cloud Run and Artifact Registry region, for example `us-central1`.
- `GCP_ARTIFACT_REPOSITORY`: Docker repository name, default `shinkai`.
- `GCP_WORKLOAD_IDENTITY_PROVIDER`: full Workload Identity Provider resource name.
- `GCP_SERVICE_ACCOUNT`: deployer service account email.
- `CLOUD_RUN_API_SERVICE`: optional, default `shinkai-api`.
- `CLOUD_RUN_WEB_SERVICE`: optional, default `shinkai-web`.
- `CLOUD_RUN_API_FLAGS`: optional, default `--allow-unauthenticated`.
- `CLOUD_RUN_WEB_FLAGS`: optional, default `--allow-unauthenticated`.
- `CLOUD_RUN_DEPLOY_ENABLED`: set to `true` only after billing and secrets are ready.

Pushes to `main` always run verification. Deployment is skipped until `GCP_PROJECT_ID`,
`GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`, and `CLOUD_RUN_DEPLOY_ENABLED=true` are
set. Manual `workflow_dispatch` runs fail fast with a configuration error if any required setting
is missing.

The deployer service account needs Cloud Run Admin, Artifact Registry Writer, Service Account
User, and access to the Secret Manager secrets referenced below.

## Secrets

Create these Google Secret Manager secrets:

```bash
gcloud secrets create shinkai-admin-token --replication-policy=automatic
printf '%s' '<strong-admin-token>' | gcloud secrets versions add shinkai-admin-token --data-file=-

gcloud secrets create deepseek-api-key --replication-policy=automatic
printf '%s' '<deepseek-api-key>' | gcloud secrets versions add deepseek-api-key --data-file=-
```

Cloud Run receives them as:

- `SHINKAI_ADMIN_TOKEN`
- `SHINKAI_DEEPSEEK_API_KEY`

For durable backend state, provision a Postgres-compatible database such as Cloud SQL for
PostgreSQL and set `SHINKAI_DATABASE_URL` on the API service. When
`SHINKAI_PERSISTENCE_JSON_FALLBACK=true`, the API falls back to `SHINKAI_STATE_PATH` if Postgres is
not configured or temporarily unavailable.

## Access Model

Cloud Run can be publicly invokable so ordinary users can view published results and the agent
running process. Application-level authorization protects all write operations:

- Public: `GET /health`, runs, graphs, eval reports, checkpoints, A2A message list, event streams.
- Subscriber-ready: future subscription tokens can expand read scope to extended results and
  history without granting write access.
- Admin only: creating runs, starting/pausing/aborting runs, releasing checkpoints, and creating A2A messages.

The web app stores the admin token in browser `localStorage` only after manual admin login. Users
without the token remain in read-only mode. Admin sessions expose all capabilities; ordinary viewer
sessions expose `read_results` and `read_run_process`.

## Local Production Check

```bash
docker build -f services/api/Dockerfile -t shinkai-api .
docker build -f apps/web/Dockerfile \
  --build-arg NEXT_PUBLIC_API_URL=http://localhost:8100 \
  -t shinkai-web .
```

For production durability, prefer Cloud SQL/PostgreSQL through `SHINKAI_DATABASE_URL` rather than a
container-local JSON state path.
