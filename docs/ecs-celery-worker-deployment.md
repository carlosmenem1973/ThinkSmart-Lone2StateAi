# ECS deployment: ThinkSmart Celery worker and Beat

## Topology

The GitLab rollout uses AWS CLI against pre-existing ECS resources. OpenTofu files remain for infrastructure validation/reference and are not applied by the deployment pipeline. The pipeline expects these three Fargate services to exist in the approved cluster:

| Service | Process | Desired count |
|---|---|---:|
| API | FastAPI | Existing API setting |
| Worker | Celery Worker | `worker_desired_count` |
| Beat | Celery Beat | Exactly 1 when enabled |

Worker consumes tasks; Beat publishes periodic tasks. Never run `celery worker --beat` in the worker service and never horizontally scale Beat. The Beat ECS service uses a non-overlapping deployment (`maximum_percent=100`) to prevent two active schedulers during replacement.

## Task definitions

The following task-definition families/services must be provisioned before the AWS CLI deployment job can run:
- `thinksmart-lone2stateai-prod-api`
- `thinksmart-lone2stateai-prod-worker`
- `thinksmart-lone2stateai-prod-beat`

API, Worker and Beat task definitions are updated to the same immutable image URI in the existing ECR repository. The pipeline does not create ECR repositories, ECS services, queues, Redis or IAM policies.

Worker command:

```bash
celery -A app.workers.celery_app.celery worker --loglevel=INFO --concurrency=2
```

Beat command:

```bash
celery -A app.workers.celery_app.celery beat --loglevel=INFO
```

Do not apply a HTTP health check to Worker or Beat.

## Runtime secrets and outbound provider configuration

The application Secrets Manager JSON contains the Meta and SES settings used by the API and Worker:
- `META_WHATSAPP_ACCESS_TOKEN`
- `META_WHATSAPP_PHONE_NUMBER_ID`
- `META_WHATSAPP_APP_SECRET`
- `META_WHATSAPP_VERIFY_TOKEN`
- `META_GRAPH_API_VERSION`
- `EMAIL_FROM_ADDRESS`
- `SES_SENDER_VERIFIED`

GitLab deployment variables populate only explicitly supplied keys through `scripts/aws/merge-runtime-secrets.sh`. Existing JSON keys are preserved. The older `set-runtime-secrets.sh` is not used by the pipeline because it replaces the complete JSON document.

SES:
- Sender: `contacto@cbloft2.pt`
- Region: `eu-west-1`
- IAM Task Role policy grants `ses:SendEmail` only for the `cbloft2.pt` SES identity.
- Set `SES_SENDER_VERIFIED=true` only after verifying the SES identity and DKIM. Check whether SES is in sandbox and request production access if required.
- Preserve the existing Microsoft 365 SPF configuration. Publish one consolidated SPF record; do not add a second SPF TXT record.

Meta:
- Configure the WhatsApp Business number and Meta app.
- Configure the webhook URL and verify token, and subscribe to required WhatsApp webhook events.
- Test with approved test recipients before enabling outbound delivery.

The infrastructure does not verify SES DNS or Meta ownership; these are external operational prerequisites.

## Network and IAM

Worker and Beat run in private subnets using the ECS task security group. They require Redis TCP 6379, PostgreSQL TCP 5432 and outbound HTTPS to Bedrock/AgentCore, Meta Graph API and AWS SES. RDS and Redis remain private.

## Migrations and rollout

Run Alembic exactly once as a controlled one-off ECS task with the approved release image:

```bash
alembic upgrade head
alembic current
```

Use the actual current head revision from the approved release. Do not hard-code the old `0006_property_discovery` revision; this branch includes later migrations, including `0009_communications` and `0010_communications_outbox`.

Rollout order:
1. Obtain green CI and approve the PR.
2. Confirm by AWS CLI that the existing ECS cluster, API/Worker/Beat services, encrypted SQS FIFO queue, Redis, ECR, Secrets Manager secret, S3 bucket and CloudFront distribution are present.
3. Trigger the manual GitLab AWS CLI deployment job. It performs a read-only preflight before any remote writes and fails closed if a required resource is missing.
4. The pipeline builds the artifacts, pushes one immutable image, merges only explicitly configured secret keys, and registers new revisions of the existing task definitions.
5. Run `alembic upgrade head` once as a one-off ECS task and verify its exit code. The pipeline does not update any service if migration fails.
6. Update the three existing ECS services and wait for them to stabilize; Beat must remain at desired count exactly 1.
7. Verify CloudWatch logs and scheduled task publication.
8. Configure SES and Meta while outbound channels remain disabled.
9. Enable channels only after legal, operational and human approval.

The GitLab deployment jobs are manual and run only from `main`. They do not bootstrap or provision infrastructure. The preflight requires Beat to be already running with desired count exactly 1.

## Delivery reliability boundary

The approval route commits the message and its outbox row atomically. Celery Beat schedules the outbox relay; the Worker publishes only the message ID to an encrypted SQS FIFO queue and consumes it. The queue has a DLQ with a five-receive redrive threshold and a CloudWatch alarm when visible DLQ messages exist. Ensure the SNS alerts topic has an operational subscription. The consumer revalidates consent and channel state before delivery and marks ambiguous outcomes as `delivery_uncertain` rather than blindly retrying. Validate DLQ/redrive, duplicate delivery and failure-recovery behavior in staging before enabling production outbound messaging. Provider delivery/read callbacks are not yet persisted.

A message marked `sent` currently means the provider accepted the request, not that the recipient received or read it. Never blindly retry a message left in `sending` after an ambiguous provider response.

## Acceptance checklist

- [ ] Worker starts and registers expected Celery tasks.
- [ ] Beat starts and publishes scheduled entries.
- [ ] Exactly one Beat task is active.
- [ ] Worker and Beat connect to Redis and PostgreSQL.
- [ ] API, Worker and Beat logs are separated in CloudWatch.
- [ ] SES identity/DKIM and send permission are verified.
- [ ] Meta webhook verification and deduplication are tested.
- [ ] Outbound channels remain disabled until explicit operational approval.
- [ ] Automated property discovery does not create CRM leads or contact owners.
