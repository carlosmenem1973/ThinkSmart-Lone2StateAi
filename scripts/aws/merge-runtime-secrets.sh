#!/usr/bin/env bash
set -euo pipefail

# Merge explicitly supplied runtime settings into an existing JSON secret.
# Existing keys are preserved; secret contents never enter command arguments or logs.

: "${AWS_REGION:?Set AWS_REGION}"
: "${APP_SECRET_ID:?Set APP_SECRET_ID to the existing application secret name or ARN}"

CURRENT_FILE="$(mktemp)"
OUTPUT_FILE="$(mktemp)"
chmod 600 "$CURRENT_FILE" "$OUTPUT_FILE"
cleanup() {
  rm -f "$CURRENT_FILE" "$OUTPUT_FILE"
}
trap cleanup EXIT

aws secretsmanager get-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$APP_SECRET_ID" \
  --query SecretString \
  --output text > "$CURRENT_FILE"

python3 - "$CURRENT_FILE" "$OUTPUT_FILE" <<'PY'
import json
import os
import sys

source_path, output_path = sys.argv[1:3]
with open(source_path, encoding="utf-8") as source:
    secret = json.load(source)
if not isinstance(secret, dict):
    raise SystemExit("Existing Secrets Manager value must be a JSON object")

allowed = (
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
)
for key in allowed:
    value = os.environ.get(key)
    if value is not None and value != "":
        secret[key] = value

with open(output_path, "w", encoding="utf-8") as output:
    json.dump(secret, output, separators=(",", ":"))
PY

aws secretsmanager put-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$APP_SECRET_ID" \
  --secret-string "file://$OUTPUT_FILE" >/dev/null

printf 'Runtime secret updated selectively; existing keys were preserved.\n'
