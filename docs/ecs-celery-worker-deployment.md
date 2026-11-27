# ECS deployment: ThinkSmart Celery worker and Beat

## Topology

OpenTofu defines three independent Fargate services in the existing cluster:

| Service | Process | Desired count |
|---|---|---:|
| API | FastAPI | Existing API setting |
| Worker | Celery Worker | `worker_desired_count` |
| Beat | Celery Beat | Exactly 1 when enabled |

Worker consumes tasks; Beat publishes periodic tasks. Never run `celery worker --beat` in the worker service and never horizontally scale Beat. The Beat ECS service uses a non-overlapping deployment (`maximum_percent=100`) to prevent two active schedulers during replacement.

## Task definitions

Task definition families:
- `thinksmart-lone2stateai-prod-api`
- `thinksmart-lone2stateai-prod-worker`
- `thinksmart-lone2stateai-prod-beat`

Worker and Beat use the worker ECR repository and the same immutable image tag as the API release. The GitLab deployment pipeline builds once, pushes the API image, tags the same image for the worker repository, and waits for all three ECS services to stabilize.

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

New keys are initially empty/defaulted by infrastructure. GitLab deployment variables may populate them through `scripts/aws/set-runtime-secrets.sh`. Use protected/masked GitLab variables for tokens and secrets; never commit their values.

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
2. Build/push the backend image to API and worker ECR repositories.
3. Review the OpenTofu plan before applying.
4. Deploy API and run the migration once.
5. Start Worker with desired count 1 initially.
6. Start Beat with desired count exactly 1.
7. Verify CloudWatch logs and scheduled task publication.
8. Configure SES and Meta while outbound channels remain disabled.
9. Enable channels only after legal, operational and human approval.

The GitLab pipeline sets Beat to zero during bootstrap, then to one only after runtime secrets are populated. Production deployment remains manual.

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
