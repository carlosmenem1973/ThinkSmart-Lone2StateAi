#!/usr/bin/env bash
set -euo pipefail

required=(
  AWS_REGION AWS_ACCOUNT_ID ECR_REPOSITORY_NAME
  ECS_CLUSTER_NAME ECS_API_SERVICE_NAME ECS_API_CONTAINER_NAME IMAGE_TAG
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

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
[[ "$ACCOUNT" == "$AWS_ACCOUNT_ID" ]] || {
  echo "AWS account mismatch; refusing deployment" >&2
  exit 2
}

CLUSTER_ARN="$(aws ecs describe-clusters --clusters "$ECS_CLUSTER_NAME" \
  --query 'clusters[?status==`ACTIVE`].clusterArn | [0]' --output text)"
[[ -n "$CLUSTER_ARN" && "$CLUSTER_ARN" != "None" ]] || {
  echo "ECS cluster is not ACTIVE" >&2
  exit 2
}

SERVICE_JSON="$(aws ecs describe-services --cluster "$ECS_CLUSTER_NAME" \
  --services "$ECS_API_SERVICE_NAME" --output json)"
printf '%s' "$SERVICE_JSON" | jq -e --arg name "$ECS_API_SERVICE_NAME" '
  (.failures | length) == 0 and
  (.services | length) == 1 and
  .services[0].serviceName == $name and
  .services[0].status == "ACTIVE" and
  .services[0].desiredCount >= 1 and
  (.services[0].taskDefinition | type == "string")
' >/dev/null || {
  echo "The configured API ECS service must already exist and be ACTIVE" >&2
  exit 2
}

TASK_OLD="$(printf '%s' "$SERVICE_JSON" | jq -r '.services[0].taskDefinition')"
API_NETWORK="$(printf '%s' "$SERVICE_JSON" | jq -c '.services[0].networkConfiguration')"
[[ -n "$TASK_OLD" && "$TASK_OLD" != "null" && "$API_NETWORK" != "null" ]] || {
  echo "Could not read API task definition or awsvpc network configuration" >&2
  exit 2
}

TASK_SOURCE="$(mktemp)"
TASK_INPUT="$(mktemp)"
trap 'rm -f "$TASK_SOURCE" "$TASK_INPUT"' EXIT

aws ecs describe-task-definition --task-definition "$TASK_OLD" \
  --query taskDefinition --output json > "$TASK_SOURCE"

jq -e --arg name "$ECS_API_CONTAINER_NAME" \
  'any(.containerDefinitions[]; .name == $name)' "$TASK_SOURCE" >/dev/null || {
  echo "Container '$ECS_API_CONTAINER_NAME' not found in $TASK_OLD" >&2
  exit 2
}

IMAGE_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}:${IMAGE_TAG}"
aws ecr describe-repositories --repository-names "$ECR_REPOSITORY_NAME" >/dev/null

# Build and push only the API image. No infrastructure or runtime secrets are changed.
aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
docker build --pull -f backend/Dockerfile -t "$IMAGE_URI" backend
docker push "$IMAGE_URI"

jq --arg image "$IMAGE_URI" --arg cname "$ECS_API_CONTAINER_NAME" '
  .containerDefinitions |= map(
    if .name == $cname then .image = $image else . end
  ) |
  del(.taskDefinitionArn, .revision, .status, .requiresAttributes,
      .compatibilities, .registeredAt, .registeredBy)
' "$TASK_SOURCE" > "$TASK_INPUT"

TASK_NEW="$(aws ecs register-task-definition --cli-input-json "file://$TASK_INPUT" \
  --query 'taskDefinition.taskDefinitionArn' --output text)"
[[ -n "$TASK_NEW" && "$TASK_NEW" != "None" ]] || {
  echo "Could not register the new API task definition" >&2
  exit 1
}

# Run the migration with the API service's existing private network configuration.
MIGRATION_OVERRIDES="$(jq -cn --arg name "$ECS_API_CONTAINER_NAME" \
  '{containerOverrides:[{name:$name,command:["alembic","upgrade","head"]}]}')"
MIGRATION_RUN="$(aws ecs run-task --cluster "$ECS_CLUSTER_NAME" \
  --task-definition "$TASK_NEW" --launch-type FARGATE \
  --network-configuration "$API_NETWORK" --overrides "$MIGRATION_OVERRIDES" \
  --started-by "thinksmart-api-migration" --output json)"
printf '%s' "$MIGRATION_RUN" | jq -e '(.failures | length) == 0 and (.tasks | length) == 1' >/dev/null || {
  echo "Could not start the migration task; API service was not updated" >&2
  exit 1
}

MIGRATION_ARN="$(printf '%s' "$MIGRATION_RUN" | jq -r '.tasks[0].taskArn')"
aws ecs wait tasks-stopped --cluster "$ECS_CLUSTER_NAME" --tasks "$MIGRATION_ARN"
MIGRATION_INFO="$(aws ecs describe-tasks --cluster "$ECS_CLUSTER_NAME" --tasks "$MIGRATION_ARN" --output json)"
MIGRATION_EXIT="$(printf '%s' "$MIGRATION_INFO" | jq -r --arg name "$ECS_API_CONTAINER_NAME" \
  '.tasks[0].containers[] | select(.name == $name) | .exitCode // empty')"
[[ "$MIGRATION_EXIT" == "0" ]] || {
  echo "Alembic migration failed (container exit code: ${MIGRATION_EXIT:-unknown}); API service was not updated" >&2
  exit 1
}

aws ecs update-service --cluster "$ECS_CLUSTER_NAME" --service "$ECS_API_SERVICE_NAME" \
  --task-definition "$TASK_NEW" >/dev/null
aws ecs wait services-stable --cluster "$ECS_CLUSTER_NAME" --services "$ECS_API_SERVICE_NAME"

printf 'API deployment completed. Image: %s\n' "$IMAGE_URI"
