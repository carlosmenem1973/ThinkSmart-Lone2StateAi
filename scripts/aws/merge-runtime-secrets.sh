#!/usr/bin/env bash
set -euo pipefail

# Merge only explicitly supplied runtime keys into an existing Secrets Manager
# JSON document. Unspecified keys are preserved. This script does not provision
# IAM, ECS, queues, networking, or deploy application code.

: "${AWS_REGION:?Set AWS_REGION}"
: "${APP_SECRET_ID:?Set APP_SECRET_ID to the existing application secret name or ARN}"

CURRENT_SECRET="$(aws secretsmanager get-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$APP_SECRET_ID" \
  --query SecretString --output text)"

TMP_FILE="$(mktemp)"
chmod 600 "$TMP_FILE"
trap 'rm -f "$TMP_FILE"; unset CURRENT_SECRET' EXIT

export CURRENT_SECRET
python3 - "$TMP_FILE" <<'PY'
import json
import os
import sys

secret = json.loads(os.environ["CURRENT_SECRET"])
if not isinstance(secret, dict):
    raise SystemExit("Existing Secrets Manager value must be a JSON object")

# Only non-empty values explicitly supplied by the operator are changed.
allowed = {
    "META_WHATSAPP_ACCESS_TOKEN",
    "META_WHATSAPP_PHONE_NUMBER_ID",
    "META_WHATSAPP_APP_SECRET",
    "META_WHATSAPP_VERIFY_TOKEN",
    "META_GRAPH_API_VERSION",
    "EMAIL_FROM_ADDRESS",
    "SES_SENDER_VERIFIED",
    "MICROSOFT_TENANT_ID",
    "MICROSOFT_CLIENT_ID",
    "MICROSOFT_CLIENT_SECRET",
    "MICROSOFT_GRAPH_SENDER",
    "COMMUNICATIONS_SQS_QUEUE_URL",
    "REDIS_URL",
}
for key in allowed:
    value = os.environ.get(key)
    if value is not None and value != "":
        secret[key] = value

with open(sys.argv[1], "w", encoding="utf-8") as output:
    json.dump(secret, output, separators=(",", ":"))
PY

aws secretsmanager put-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$APP_SECRET_ID" \
  --secret-string "file://$TMP_FILE" >/dev/null

printf 'Updated only explicitly supplied runtime keys; all other secret keys were preserved.\n'
