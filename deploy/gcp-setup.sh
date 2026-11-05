#!/usr/bin/env bash
# One-time Google Cloud setup for the Phase 1 backend in Mumbai (asia-south1) - PRD R3, R9, R10.
# Run from the repo root by someone with Owner on the project:  PROJECT_ID=... ./deploy/gcp-setup.sh
# Prerequisites you create in the console first: the OAuth consent screen + a "Web" OAuth client
# (gmail.readonly), plus Android and iOS OAuth clients for the app (see deploy/README.md).
set -euo pipefail
: "${PROJECT_ID:?set PROJECT_ID}"
REGION=asia-south1
SERVICE=srt-backend
SA=srt-backend@${PROJECT_ID}.iam.gserviceaccount.com
PUSH_SA=srt-pubsub-push@${PROJECT_ID}.iam.gserviceaccount.com
gcloud config set project "$PROJECT_ID"

gcloud services enable run.googleapis.com sqladmin.googleapis.com cloudkms.googleapis.com pubsub.googleapis.com \
  cloudscheduler.googleapis.com secretmanager.googleapis.com gmail.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com

gcloud iam service-accounts create srt-backend --display-name "SRT backend" 2>/dev/null || true
gcloud iam service-accounts create srt-pubsub-push --display-name "SRT Pub/Sub push" 2>/dev/null || true

# R10: KMS key for envelope-encrypting OAuth tokens (India region).
gcloud kms keyrings create srt --location "$REGION" 2>/dev/null || true
gcloud kms keys create oauth-tokens --keyring srt --location "$REGION" --purpose encryption \
  --rotation-period 90d --next-rotation-time "$(date -u -d '+90 days' +%Y-%m-%dT%H:%M:%SZ)" 2>/dev/null || true
gcloud kms keys add-iam-policy-binding oauth-tokens --keyring srt --location "$REGION" \
  --member "serviceAccount:$SA" --role roles/cloudkms.cryptoKeyEncrypterDecrypter >/dev/null

# R9: PostgreSQL in Mumbai.
gcloud sql instances create srt-db --database-version POSTGRES_16 --region "$REGION" --tier db-g1-small \
  --storage-auto-increase --backup 2>/dev/null || true
gcloud sql databases create srt --instance srt-db 2>/dev/null || true
DB_PASS=$(openssl rand -base64 30 | tr -d '/+=')
gcloud sql users create srt --instance srt-db --password "$DB_PASS" 2>/dev/null || echo "db user exists; keep the existing password secret"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$SA" --role roles/cloudsql.client >/dev/null

# Secrets (values you paste are read from the environment, never echoed).
put() { printf '%s' "$2" | gcloud secrets create "$1" --data-file=- 2>/dev/null || printf '%s' "$2" | gcloud secrets versions add "$1" --data-file=-;
        gcloud secrets add-iam-policy-binding "$1" --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor >/dev/null; }
CONN=$(gcloud sql instances describe srt-db --format 'value(connectionName)')
put srt-database-url "postgresql+psycopg://srt:${DB_PASS}@/srt?host=/cloudsql/${CONN}"
put srt-jwt-secret "$(openssl rand -base64 48)"
put srt-internal-token "$(openssl rand -hex 32)"
put srt-google-client-secret "${GOOGLE_OAUTH_CLIENT_SECRET:?export the Web OAuth client secret}"
put srt-openrouter-key "${OPENROUTER_API_KEY:-unset}"
put srt-smtp-password "${SMTP_PASSWORD:-unset}"

# R3: Gmail push. Gmail's publisher must be allowed to publish to the topic.
gcloud pubsub topics create gmail-push 2>/dev/null || true
gcloud pubsub topics add-iam-policy-binding gmail-push \
  --member serviceAccount:gmail-api-push@system.gserviceaccount.com --role roles/pubsub.publisher >/dev/null

# Build and deploy (Cloud Run, Mumbai). Min 1 instance so background syncs are not frozen between requests.
gcloud artifacts repositories create srt --repository-format docker --location "$REGION" 2>/dev/null || true
IMAGE=${REGION}-docker.pkg.dev/${PROJECT_ID}/srt/backend:$(git rev-parse --short HEAD)
gcloud builds submit --tag "$IMAGE" --region "$REGION" --config /dev/stdin . <<YAML
steps:
- name: gcr.io/cloud-builders/docker
  args: [build, -f, backend/Dockerfile, -t, $IMAGE, .]
images: [$IMAGE]
YAML
gcloud run deploy "$SERVICE" --image "$IMAGE" --region "$REGION" --service-account "$SA" \
  --add-cloudsql-instances "$CONN" --min-instances 1 --no-cpu-throttling --allow-unauthenticated \
  --set-env-vars "ENV=production,REGION=${REGION},EXTRACTION_PROVIDER=openrouter,GOOGLE_OAUTH_CLIENT_ID=${GOOGLE_OAUTH_CLIENT_ID:?},KMS_KEY_NAME=projects/${PROJECT_ID}/locations/${REGION}/keyRings/srt/cryptoKeys/oauth-tokens,PUBSUB_TOPIC=projects/${PROJECT_ID}/topics/gmail-push,PUBSUB_SERVICE_ACCOUNT=${PUSH_SA},OPENROUTER_TRIAGE_MODEL=${OPENROUTER_TRIAGE_MODEL:-unset},OPENROUTER_EXTRACT_MODEL=${OPENROUTER_EXTRACT_MODEL:-unset},SMTP_HOST=${SMTP_HOST:-},SMTP_USER=${SMTP_USER:-},MAIL_FROM=${MAIL_FROM:-}" \
  --set-secrets "DATABASE_URL=srt-database-url:latest,JWT_SECRET=srt-jwt-secret:latest,INTERNAL_TOKEN=srt-internal-token:latest,GOOGLE_OAUTH_CLIENT_SECRET=srt-google-client-secret:latest,OPENROUTER_API_KEY=srt-openrouter-key:latest,SMTP_PASSWORD=srt-smtp-password:latest"
URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')
gcloud run services update "$SERVICE" --region "$REGION" --update-env-vars "PUBSUB_AUDIENCE=${URL}/pubsub/gmail"

# Push subscription with an OIDC token the backend verifies.
gcloud pubsub subscriptions create gmail-push-sub --topic gmail-push --push-endpoint "${URL}/pubsub/gmail" \
  --push-auth-service-account "$PUSH_SA" --push-auth-token-audience "${URL}/pubsub/gmail" --ack-deadline 60 2>/dev/null || true

# R7: alert tick every 5 minutes (also renews Gmail watches before their 7-day expiry).
TOKEN=$(gcloud secrets versions access latest --secret srt-internal-token)
gcloud scheduler jobs create http srt-tick --location "$REGION" --schedule "*/5 * * * *" --uri "${URL}/internal/tick" \
  --http-method POST --headers "X-Internal-Token=${TOKEN}" 2>/dev/null || \
gcloud scheduler jobs update http srt-tick --location "$REGION" --schedule "*/5 * * * *" --uri "${URL}/internal/tick" \
  --http-method POST --update-headers "X-Internal-Token=${TOKEN}"
echo "Backend: ${URL}  (set EXPO_PUBLIC_API_URL to this for the app build)"
