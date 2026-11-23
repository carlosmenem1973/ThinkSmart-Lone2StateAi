# ECS deployment: ThinkSmart Celery worker and Beat

## Purpose

The API container does not execute Celery Beat. Automated property discovery requires a running Celery worker **and exactly one Beat scheduler**. Run these as separate ECS services in the existing `thinksmart-cluster`, using the same immutable ECR image as the API.

- `thinksmart-worker`: Celery worker; desired count may be 1 or more.
- `thinksmart-beat`: Celery Beat; desired count must remain **1**.
- `thinksmart-api`: FastAPI; unchanged.

Do not run Beat in every worker replica. The task code uses a PostgreSQL row lock to reduce duplicate scheduled runs, but a single Beat remains the intended topology.

## Required task configuration

Create two task-definition families from the current production API task definition. Preserve the existing:
- Fargate launch type and `awsvpc` network mode
- execution role and task role
- Secrets Manager references (DATABASE_URL and any existing required secrets)
- environment variables, including Redis URL, AWS region, Bedrock model/profile and AgentCore Web Search settings
- CloudWatch log group `/ecs/thinksmart-api` (use distinct stream prefixes such as `worker` and `beat`)
- CPU/memory and private subnet/security-group configuration appropriate to the workload

Use the exact same ECR image digest as the API release. Do not copy credentials into task-definition environment literals.

### Container command overrides

For the worker task, override the container command to:

```json
["celery", "-A", "app.workers.celery_app.celery", "worker", "--loglevel=INFO", "--concurrency=2"]
```

For the Beat task, override the container command to:

```json
["celery", "-A", "app.workers.celery_app.celery", "beat", "--loglevel=INFO"]
```

Keep the API container health check only on the API task. Worker and Beat should use ECS container health checks appropriate to the process or rely on ECS task health plus CloudWatch alarms; do not use the API HTTP health check against these commands.

## Networking

Both services need outbound connectivity to:
- the existing Redis broker/backend
- the existing RDS PostgreSQL database
- AWS Bedrock Runtime and Bedrock AgentCore Web Search endpoints

Use the existing VPC private subnets and security group pattern. Ensure Redis and RDS security groups allow inbound traffic from the ECS task security group on their respective ports. Provide NAT or suitable VPC endpoints for AWS service access. Do not make RDS or Redis publicly accessible.

## Rollout sequence

1. Build and push the new backend image to ECR.
2. Register the API task definition using that image and deploy the API service.
3. Run the Alembic upgrade as a one-off ECS task using the same image and production environment/secrets:
   `alembic upgrade head`
4. Verify `alembic current` reports `0006_property_discovery`.
5. Register worker and Beat task definitions with the same image digest and required environment/secrets.
6. Create/update `thinksmart-worker` with desired count 1.
7. Create/update `thinksmart-beat` with desired count exactly 1.
8. Check CloudWatch logs for task registration and successful scheduler ticks.
9. Only then enable automatic discovery in the Contact AI admin panel.

Do not run the migration concurrently from every API replica. Run it once as a controlled one-off task before enabling the new worker.

## Operational checks

- Worker logs should show task execution for `app.workers.contact_ai_tasks.run_scheduled_property_discovery`.
- Beat logs should show the `property-discovery-scheduler` entry every 300 seconds.
- A disabled configuration should return without making a Bedrock request.
- Discovery reports are written to the existing `audit_logs` table and require human review.
- Set CloudWatch alarms for worker/Beat task count zero, repeated task failures, and ECS deployment failures.
- Keep Beat at one active task. If replacing it, stop the old task before allowing the replacement to become the active scheduler.

## Safety boundary

This scheduler performs web research and stores reports. It does not create CRM leads, send email/SMS/WhatsApp, or call property owners. Owner contact requires a separate, consent-aware and legally reviewed workflow with explicit human approval.
