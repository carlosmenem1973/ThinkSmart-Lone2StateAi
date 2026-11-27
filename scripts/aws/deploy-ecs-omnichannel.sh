#!/usr/bin/env bash
set -euo pipefail

required=(
  AWS_REGION AWS_ACCOUNT_ID ECR_REPOSITORY_NAME
  ECS_CLUSTER_NAME ECS_API_SERVICE_NAME ECS_WORKER_SERVICE_NAME ECS_BEAT_SERVICE_NAME
  ECS_API_CONTAINER_NAME ECS_WORKER_CONTAINER_NAME ECS_BEAT_CONTAINER_NAME
  APP_SECRET_ID COMMUNICATIONS_SQS_QUEUE_URL REDIS_URL
  FRONTEND_BUCKET CLOUDFRONT_DISTRIBUTION_ID IMAGE_TAG
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required deployment variable: $name" >&2
    exit 2
  fi
done

command -v aws >/dev/null
command -v jq >/dev/null
command -v docker >/dev/null
command -v npm >/dev/null

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
[[ "$ACCOUNT" == "$AWS_ACCOUNT_ID" ]] || {
  echo "AWS account mismatch; refusing deployment" >&2
  exit 2
}

# Read-only preflight: all runtime dependencies must already exist.
aws ecs describe-clusters --clusters "$ECS_CLUSTER_NAME" --query 'clusters[?status==`ACTIVE`].clusterArn' --output text | grep -q .
SERVICES_JSON="$(aws ecs describe-services --cluster "$ECS_CLUSTER_NAME" \
  --services "$ECS_API_SERVICE_NAME" "$ECS_WORKER_SERVICE_NAME" "$ECS_BEAT_SERVICE_NAME" --output json)"
printf '%s' "$SERVICES_JSON" | jq -e '
  (.failures | length) == 0 and
  (.services | length) == 3 and
  all(.services[]; .status == "ACTIVE" and (.taskDefinition | type == "string"))
' >/dev/null || {
  echo "API, Worker and Beat ECS services must already exist and be ACTIVE. No resources will be provisioned by this pipeline." >&2
  exit 2
}

QUEUE_ATTRIBUTES="$(aws sqs get-queue-attributes --queue-url "$COMMUNICATIONS_SQS_QUEUE_URL" \
  --attribute-names FifoQueue KmsMasterKeyId SqsManagedSseEnabled --output json)"
printf '%s' "$QUEUE_ATTRIBUTES" | jq -e '
  .Attributes.FifoQueue == "true" and
  ((.Attributes.KmsMasterKeyId // "") != "" or (.Attributes.SqsManagedSseEnabled // "false") == "true")
' >/dev/null || {
  echo "Communications queue must be FIFO and encrypted" >&2
  exit 2
}

aws ecr describe-repositories --repository-names "$ECR_REPOSITORY_NAME" >/dev/null
aws secretsmanager describe-secret --secret-id "$APP_SECRET_ID" >/dev/null
aws s3api head-bucket --bucket "$FRONTEND_BUCKET" >/dev/null
aws cloudfront get-distribution --id "$CLOUDFRONT_DISTRIBUTION_ID" >/dev/null

API_TASK_OLD="$(printf '%s' "$SERVICES_JSON" | jq -r --arg n "$ECS_API_SERVICE_NAME" '.services[] | select(.serviceName==$n) | .taskDefinition')"
WORKER_TASK_OLD="$(printf '%s' "$SERVICES_JSON" | jq -r --arg n "$ECS_WORKER_SERVICE_NAME" '.services[] | select(.serviceName==$n) | .taskDefinition')"
BEAT_TASK_OLD="$(printf '%s' "$SERVICES_JSON" | jq -r --arg n "$ECS_BEAT_SERVICE_NAME" '.services[] | select(.serviceName==$n) | .taskDefinition')"
API_NETWORK="$(printf '%s' "$SERVICES_JSON" | jq -c --arg n "$ECS_API_SERVICE_NAME" '.services[] | select(.serviceName==$n) | .networkConfiguration')"
[[ -n "$API_TASK_OLD" && "$API_TASK_OLD" != "null" && "$API_NETWORK" != "null" ]] || {
  echo "Could not read API task definition or awsvpc network configuration" >&2
  exit 2
}

aws ecs describe-task-definition --task-definition "$API_TASK_OLD" >/dev/null
aws ecs describe-task-definition --task-definition "$WORKER_TASK_OLD" >/dev/null
aws ecs describe-task-definition --task-definition "$BEAT_TASK_OLD" >/dev/null

IMAGE_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}:${IMAGE_TAG}"
APP_SECRET_ARN="$(aws secretsmanager describe-secret --secret-id "$APP_SECRET_ID" --query ARN --output text)"

# Build the frontend and backend artifacts before any remote write.
(cd frontend && npm ci --no-audit --no-fund && npm run build)
aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
docker build --pull -f backend/Dockerfile -t "$IMAGE_URI" backend
docker push "$IMAGE_URI"

# Update only explicitly supplied secret keys. Existing JSON keys are retained.
export AWS_REGION APP_SECRET_ID COMMUNICATIONS_SQS_QUEUE_URL REDIS_URL
bash scripts/aws/merge-runtime-secrets.sh

# Add ECS JSON-key references only for keys explicitly configured in this job.
runtime_keys=(
  META_WHATSAPP_ACCESS_TOKEN META_WHATSAPP_PHONE_NUMBER_ID META_WHATSAPP_APP_SECRET
  META_WHATSAPP_VERIFY_TOKEN META_GRAPH_API_VERSION EMAIL_FROM_ADDRESS SES_SENDER_VERIFIED
  MICROSOFT_TENANT_ID MICROSOFT_CLIENT_ID MICROSOFT_CLIENT_SECRET MICROSOFT_GRAPH_SENDER
  COMMUNICATIONS_SQS_QUEUE_URL REDIS_URL
)
configured_keys=()
for key in "${runtime_keys[@]}"; do
  [[ -n "${!key:-}" ]] && configured_keys+=("$key")
done
KEYS_JSON="$(printf '%s\n' "${configured_keys[@]}" | jq -Rsc 'split("\n") | map(select(length>0))')"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

register_image_task_definition() {
  local old_task="$1" container_name="$2" label="$3"
  local source_file="$TMP_DIR/${label}-source.json"
  local input_file="$TMP_DIR/${label}-register.json"

  aws ecs describe-task-definition --task-definition "$old_task" \
    --query taskDefinition --output json > "$source_file"

  jq -e --arg name "$container_name" 'any(.containerDefinitions[]; .name==$name)' \
    "$source_file" >/dev/null || {
      echo "Container '$container_name' not found in task definition $old_task" >&2
      exit 2
    }

  jq --arg image "$IMAGE_URI" --arg cname "$container_name" \
    --arg arn "$APP_SECRET_ARN" --argjson keys "$KEYS_JSON" '
    .containerDefinitions |= map(
      if .name == $cname then
        .image = $image |
        .secrets = ((.secrets // [] | map(select(.name as $n | ($keys | index($n)) == null))) +
          [$keys[] as $key | {name:$key, valueFrom:($arn + ":" + $key + "::")}])
      else . end
    ) |
    del(.taskDefinitionArn, .revision, .status, .requiresAttributes,
        .compatibilities, .registeredAt, .registeredBy)
  ' "$source_file" > "$input_file"

  aws ecs register-task-definition --cli-input-json "file://$input_file" \
    --query 'taskDefinition.taskDefinitionArn' --output text
}

API_TASK_NEW="$(register_image_task_definition "$API_TASK_OLD" "$ECS_API_CONTAINER_NAME" api)"
WORKER_TASK_NEW="$(register_image_task_definition "$WORKER_TASK_OLD" "$ECS_WORKER_CONTAINER_NAME" worker)"
BEAT_TASK_NEW="$(register_image_task_definition "$BEAT_TASK_OLD" "$ECS_BEAT_CONTAINER_NAME" beat)"

# Run schema migration once using the new API image and the API service network.
MIGRATION_OVERRIDES="$(jq -cn --arg name "$ECS_API_CONTAINER_NAME" \
  '{containerOverrides:[{name:$name,command:["alembic","upgrade","head"]}]}')"
MIGRATION_RUN="$(aws ecs run-task --cluster "$ECS_CLUSTER_NAME" \
  --task-definition "$API_TASK_NEW" --launch-type FARGATE \
  --network-configuration "$API_NETWORK" --overrides "$MIGRATION_OVERRIDES" \
  --started-by "thinksmart-migration-$IMAGE_TAG" --output json)"
printf '%s' "$MIGRATION_RUN" | jq -e '(.failures | length)==0 and (.tasks | length)==1' >/dev/null || {
  echo "Could not start the migration task; application services were not updated" >&2
  exit 1
}
MIGRATION_ARN="$(printf '%s' "$MIGRATION_RUN" | jq -r '.tasks[0].taskArn')"
aws ecs wait tasks-stopped --cluster "$ECS_CLUSTER_NAME" --tasks "$MIGRATION_ARN"
MIGRATION_INFO="$(aws ecs describe-tasks --cluster "$ECS_CLUSTER_NAME" --tasks "$MIGRATION_ARN" --output json)"
MIGRATION_EXIT="$(printf '%s' "$MIGRATION_INFO" | jq -r --arg n "$ECS_API_CONTAINER_NAME" '.tasks[0].containers[] | select(.name==$n) | .exitCode // empty')"
[[ "$MIGRATION_EXIT" == "0" ]] || {
  echo "Alembic migration failed; API, Worker and Beat services were not updated" >&2
  exit 1
}

aws ecs update-service --cluster "$ECS_CLUSTER_NAME" --service "$ECS_API_SERVICE_NAME" \
  --task-definition "$API_TASK_NEW" >/dev/null
aws ecs update-service --cluster "$ECS_CLUSTER_NAME" --service "$ECS_WORKER_SERVICE_NAME" \
  --task-definition "$WORKER_TASK_NEW" >/dev/null
aws ecs update-service --cluster "$ECS_CLUSTER_NAME" --service "$ECS_BEAT_SERVICE_NAME" \
  --task-definition "$BEAT_TASK_NEW" >/dev/null

aws ecs wait services-stable --cluster "$ECS_CLUSTER_NAME" \
  --services "$ECS_API_SERVICE_NAME" "$ECS_WORKER_SERVICE_NAME" "$ECS_BEAT_SERVICE_NAME"

aws s3 sync frontend/dist "s3://${FRONTEND_BUCKET}/" --delete
aws cloudfront create-invalidation --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" \
  --paths '/*' >/dev/null

printf 'Deployment completed for API, Worker and Beat using AWS CLI. Image: %s\n' "$IMAGE_URI"
