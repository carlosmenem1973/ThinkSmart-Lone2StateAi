#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?Set AWS_REGION}"
: "${SECRET_KEY:?Set SECRET_KEY}"
: "${MICROSOFT_TENANT_ID:?Set MICROSOFT_TENANT_ID (use 'common' until tenant is configured)}"
BOOTSTRAP_ADMIN_EMAIL="${BOOTSTRAP_ADMIN_EMAIL:-}"
BOOTSTRAP_ADMIN_PASSWORD="${BOOTSTRAP_ADMIN_PASSWORD:-}"
if [ -n "$BOOTSTRAP_ADMIN_EMAIL" ] || [ -n "$BOOTSTRAP_ADMIN_PASSWORD" ]; then
  if [ -z "$BOOTSTRAP_ADMIN_EMAIL" ] || [ "${#BOOTSTRAP_ADMIN_PASSWORD}" -lt 16 ]; then
    echo "Set both bootstrap admin values; password must be at least 16 characters" >&2; exit 1
  fi
fi
TF_DIR="${TF_DIR:?Set TF_DIR to infra/env/dev or infra/env/prod}"

APP_SECRET_ARN="$(tofu -chdir="$TF_DIR" output -raw app_secret_arn)"
DB_SECRET_ARN="$(tofu -chdir="$TF_DIR" output -raw db_master_secret_arn)"
DB_ENDPOINT="$(tofu -chdir="$TF_DIR" output -raw db_endpoint)"
REDIS_ENDPOINT="$(tofu -chdir="$TF_DIR" output -raw redis_endpoint)"
DB_SECRET_JSON="$(aws secretsmanager get-secret-value --region "$AWS_REGION" --secret-id "$DB_SECRET_ARN" --query SecretString --output text)"
export DB_SECRET_JSON DB_ENDPOINT REDIS_ENDPOINT SECRET_KEY
export BOOTSTRAP_ADMIN_EMAIL BOOTSTRAP_ADMIN_PASSWORD
export MICROSOFT_TENANT_ID MICROSOFT_CLIENT_ID="${MICROSOFT_CLIENT_ID:-}"
export MICROSOFT_CLIENT_SECRET="${MICROSOFT_CLIENT_SECRET:-}"
: "${MICROSOFT_REDIRECT_URI:?Set MICROSOFT_REDIRECT_URI to the registered Entra callback URL}"
export GOOGLE_MAPS_API_KEY="${GOOGLE_MAPS_API_KEY:-}"

TMP_FILE="$(mktemp)"
chmod 600 "$TMP_FILE"
trap 'rm -f "$TMP_FILE"' EXIT

python3 - "$TMP_FILE" <<'PY'
import json, os, sys
from urllib.parse import quote

master = json.loads(os.environ["DB_SECRET_JSON"])
user = quote(master["username"], safe="")
password = quote(master["password"], safe="")
db_url = (
    f"postgresql+psycopg://{user}:{password}@{os.environ['DB_ENDPOINT']}:5432/estateai"
    "?sslmode=require"
)
redis_url = f"rediss://{os.environ['REDIS_ENDPOINT']}:6379/0"
secret = {
    "DATABASE_URL": db_url,
    "REDIS_URL": redis_url,
    "SECRET_KEY": os.environ["SECRET_KEY"],
    "BOOTSTRAP_ADMIN_EMAIL": os.environ["BOOTSTRAP_ADMIN_EMAIL"],
    "BOOTSTRAP_ADMIN_PASSWORD": os.environ["BOOTSTRAP_ADMIN_PASSWORD"],
    "MICROSOFT_TENANT_ID": os.environ["MICROSOFT_TENANT_ID"],
    "MICROSOFT_REDIRECT_URI": os.environ["MICROSOFT_REDIRECT_URI"],
    "MICROSOFT_CLIENT_ID": os.environ.get("MICROSOFT_CLIENT_ID", ""),
    "MICROSOFT_CLIENT_SECRET": os.environ.get("MICROSOFT_CLIENT_SECRET", ""),
    "GOOGLE_MAPS_API_KEY": os.environ.get("GOOGLE_MAPS_API_KEY", ""),
}
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(secret, f)
PY

aws secretsmanager put-secret-value --region "$AWS_REGION" --secret-id "$APP_SECRET_ARN" \
  --secret-string "file://$TMP_FILE" >/dev/null
printf 'Runtime secret updated: %s\n' "$APP_SECRET_ARN"
