# AWS deployment – Development and Production

This guide deploys ThinkSmart-Lone2StateAi to AWS with OpenTofu, ECS Fargate, RDS PostgreSQL, ElastiCache Redis, CloudFront, S3, an Application Load Balancer, AWS WAF, Secrets Manager and CloudWatch.

## 1. Architecture and isolation

The project has two independent OpenTofu roots:

- `infra/env/dev`: VPC `10.40.0.0/16`, one NAT gateway, single-AZ RDS, one Redis node, one API task and one worker task after activation.
- `infra/env/prod`: VPC `10.50.0.0/16`, NAT gateway per AZ, Multi-AZ RDS, two Redis cache nodes, two API tasks and one worker task after activation.

Each environment has its own ECS cluster, ECR repositories, VPC, subnets, security groups, database, Redis, Secrets Manager secret, log groups, S3 frontend bucket and CloudFront distribution. The two environments share only the AWS account and the encrypted/versioned OpenTofu state bucket (separate state keys).

CloudFront serves the React application from a private S3 bucket using Origin Access Control. `/api/*` is routed to the ALB. The ALB security group only permits the AWS-managed CloudFront origin-facing prefix list. AWS WAF protects the CloudFront distribution with AWS managed rule groups and a per-IP rate limit.

The ALB origin uses HTTP only until an API-origin ACM certificate and hostname are configured. For production, configure HTTPS origin as described in section 8.

## 2. Prerequisites

- An AWS account with permission to create VPC, ECS, ECR, RDS, ElastiCache, CloudFront, WAF, IAM, Secrets Manager, Route 53 and CloudWatch resources.
- AWS CLI v2 configured for an administrator/bootstrap identity.
- OpenTofu >= 1.10.0.
- Docker and a GitLab Runner that supports privileged Docker-in-Docker for image builds.
- A GitLab project containing this repository.
- IAM permissions for Amazon Bedrock Nova Lite inference and AgentCore Web Search.
- A Microsoft Entra application registration for Microsoft Graph mailbox access (the mailbox integration must be completed separately).

Default region: `eu-west-1` (Ireland). CloudFront WAF resources are created through an aliased provider in `us-east-1`, as required by AWS.

## 3. Create the remote state bucket

Choose a globally unique bucket name. The default is account-specific:

```bash
export AWS_REGION=eu-west-1
export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export TF_STATE_BUCKET="thinksmart-lone2stateai-tfstate-${AWS_ACCOUNT_ID}"
./scripts/aws/bootstrap-state.sh
```

The script enables S3 versioning, default encryption, public-access blocking and bucket-owner-enforced ownership. OpenTofu uses S3 native lock files (`use_lockfile=true`); no DynamoDB lock table is required. Do not delete this bucket. Restrict access to the infrastructure administrators and deployment roles.

## 4. Configure GitLab OIDC

In AWS IAM, create an OpenID Connect identity provider:

- Provider URL: `https://gitlab.com`
- Audience: `sts.amazonaws.com`

Use the provider ARN in the next step. Do not use long-lived AWS access keys in GitLab CI.

Set the exact GitLab subject for the protected `main` branch. Example (replace with the real namespace and project path):

```bash
export GITLAB_OIDC_PROVIDER_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/gitlab.com"
export GITLAB_OIDC_SUBJECT="project_path:my-group/thinksmart-lone2stateai:ref_type:branch:ref:main"
```

The OpenTofu module creates separate development and production CI roles. Their trust policy accepts only this GitLab project subject and the `sts.amazonaws.com` audience. The CI roles use `PowerUserAccess` plus a narrowly scoped IAM policy for the project-prefixed task roles, service-linked roles and `iam:PassRole`. This is a broad infrastructure-provisioning role with project-scoped trust, not a fully resource-scoped least-privilege policy. Prefer a dedicated AWS account for this application and review/tighten the policy against your organisation's IAM standards before production use.

## 5. First infrastructure bootstrap (run locally as AWS administrator)

The first apply creates the AWS resources, ECR repositories, IAM deployment roles and empty ECS services (desired count zero). It intentionally does not start containers before images and runtime secrets are available.

Development:

```bash
cd infra/env/dev
tofu init \
  -backend-config="bucket=${TF_STATE_BUCKET}" \
  -backend-config="key=thinksmart-lone2stateai/dev/terraform.tfstate" \
  -backend-config="region=${AWS_REGION}" \
  -backend-config="encrypt=true" \
  -backend-config="use_lockfile=true"
tofu plan \
  -var="gitlab_oidc_provider_arn=${GITLAB_OIDC_PROVIDER_ARN}" \
  -var="gitlab_subject=${GITLAB_OIDC_SUBJECT}" -out=dev.tfplan
tofu apply dev.tfplan
```

Production:

```bash
cd ../prod
tofu init \
  -backend-config="bucket=${TF_STATE_BUCKET}" \
  -backend-config="key=thinksmart-lone2stateai/prod/terraform.tfstate" \
  -backend-config="region=${AWS_REGION}" \
  -backend-config="encrypt=true" \
  -backend-config="use_lockfile=true"
tofu plan \
  -var="gitlab_oidc_provider_arn=${GITLAB_OIDC_PROVIDER_ARN}" \
  -var="gitlab_subject=${GITLAB_OIDC_SUBJECT}" -out=prod.tfplan
tofu apply prod.tfplan
```

The RDS master password is generated and managed by AWS Secrets Manager (`manage_master_user_password=true`); it is not supplied as an OpenTofu variable. The application secret is created with placeholders and is populated by the deployment pipeline after RDS and Redis are ready.

Get the deployment role ARNs:

```bash
cd ../dev
tofu output -raw gitlab_ci_role_arn
cd ../prod
tofu output -raw gitlab_ci_role_arn
```

Save each ARN as a protected GitLab CI/CD variable.

## 6. GitLab CI/CD variables

Create these project/group CI/CD variables. Mark credentials as **masked** and **protected** where GitLab permits; mark production variables protected. Do not commit `.env`, tokens, client secrets or API keys.

| Variable | Example / purpose |
|---|---|
| `AWS_ACCOUNT_ID` | 12-digit AWS account ID |
| `AWS_REGION` | `eu-west-1` |
| `TF_STATE_BUCKET` | Name created in section 3 |
| `GITLAB_OIDC_PROVIDER_ARN` | IAM OIDC provider ARN |
| `GITLAB_OIDC_SUBJECT` | Exact `project_path:...:ref_type:branch:ref:main` subject |
| `AWS_ROLE_ARN_DEV` | Development role ARN from tofu output |
| `AWS_ROLE_ARN_PROD` | Production role ARN from tofu output |
| — | No AI API key is required; ECS uses its task role for Bedrock and AgentCore |
| `SECRET_KEY_DEV` / `SECRET_KEY_PROD` | Separate random application signing secrets |
| `BOOTSTRAP_ADMIN_EMAIL_DEV` / `..._PROD` | Initial administrator email; remove after bootstrap |
| `BOOTSTRAP_ADMIN_PASSWORD_DEV` / `..._PROD` | Initial administrator password (16+ chars, upper/lower/digit); remove after bootstrap |
| `MICROSOFT_TENANT_ID_DEV` / `..._PROD` | Entra tenant ID |
| `MICROSOFT_CLIENT_ID_DEV` / `..._PROD` | Entra app client ID |
| `MICROSOFT_CLIENT_SECRET_DEV` / `..._PROD` | Entra app client secret |
| `GOOGLE_MAPS_API_KEY_DEV` / `..._PROD` | Optional Maps key |
| `ALB_CERTIFICATE_ARN_DEV` / `..._PROD` | Optional ACM certificate ARN for the API origin |
| `API_ORIGIN_DOMAIN_NAME_DEV` / `..._PROD` | Optional hostname covered by the ACM certificate |
| `ROUTE53_ZONE_ID_DEV` / `..._PROD` | Optional hosted-zone ID for an ALB alias record |

Generate independent application secrets, for example:

```bash
openssl rand -hex 48
```

Set the GitLab project runner to allow privileged Docker-in-Docker. The pipeline has three phases: OpenTofu validation, automatic development deployment from `main`, and a manual production deployment from `main`. The production job should be protected with GitLab protected environments and approval rules.

## 7. What the deployment pipeline does

For each environment the pipeline:

1. Assumes the environment-specific AWS role using GitLab OIDC (no static AWS keys).
2. Initializes the correct remote state key.
3. Applies infrastructure with ECS desired counts set to zero so the ECR repositories and supporting AWS services are ready first.
4. Builds the backend image once and pushes immutable pipeline-specific tags to the API and worker ECR repositories.
5. Reads the AWS-managed RDS master secret, constructs the application database URL, constructs the TLS Redis URL, and writes runtime configuration to Secrets Manager without printing secret values.
6. Applies OpenTofu again with the new image tag and desired ECS task counts.
7. Builds the React frontend, syncs it to the private S3 bucket, invalidates CloudFront and waits for ECS services to become stable.

The API and worker use the same backend image; the worker overrides the container command to run Celery.

## 8. Enable TLS from CloudFront to the ALB for production

The default CloudFront viewer connection is HTTPS. The ALB origin can start in HTTP-only mode, restricted by its security group to CloudFront's origin-facing managed prefix list. For end-to-end TLS to the origin:

1. Choose an API hostname, for example `api-estateai.example.pt`.
2. Request an ACM public certificate for that hostname in **eu-west-1**.
3. Complete ACM DNS validation before deploying the certificate.
4. Set `ALB_CERTIFICATE_ARN_PROD` to the issued certificate ARN.
5. Set `API_ORIGIN_DOMAIN_NAME_PROD` to the exact hostname on the certificate.
6. Set `ROUTE53_ZONE_ID_PROD` if the domain is hosted in Route 53. OpenTofu creates an ALB alias record. If DNS is external, create an equivalent alias/CNAME record yourself.

When `certificate_arn` is set, OpenTofu creates an HTTPS ALB listener, redirects HTTP to HTTPS, and configures CloudFront to use HTTPS to the API origin. The certificate hostname must match `api_origin_domain_name`.

The public frontend currently uses the CloudFront-generated hostname. To use a branded website hostname, add a CloudFront alias and an ACM certificate issued in **us-east-1** plus the corresponding DNS validation and alias records; that is a separate DNS configuration because the actual company domain has not yet been supplied.

## 9. Runtime secrets and Microsoft 365

`set-runtime-secrets.sh` populates the per-environment Secrets Manager JSON secret with:

- `DATABASE_URL` (RDS PostgreSQL, TLS required)
- `REDIS_URL` (ElastiCache TLS endpoint)
- `SECRET_KEY` (Bedrock access uses the ECS task role, not a stored API key)
- Microsoft tenant, client ID and client secret
- Optional Google Maps API key

ECS injects these values through the **task execution role**, which has `secretsmanager:GetSecretValue` for this one application secret. The ECS task role has narrowly scoped `bedrock:InvokeModel`, `bedrock:GetInferenceProfile`, and `bedrock-agentcore:InvokeWebSearch` permissions for the EU Nova Lite inference profile and managed Web Search tool. The deployment sets the Microsoft redirect URI to `https://<cloudfront-domain>/api/v1/integrations/microsoft/callback`. After the first development deployment, copy the CloudFront domain from `tofu output -raw cloudfront_domain` and register that exact callback URL as a **Web** redirect URI in the Microsoft Entra app registration. The app currently requests delegated `User.Read` and `Mail.Read` scopes. Its callback does not yet persist an encrypted per-seller token cache; mailbox token persistence, per-seller consent/mapping, refresh and sync workers must be implemented and tested before real mailboxes are connected.

## 10. Security controls included

- Separate VPCs and private subnets per environment; RDS and Redis are not publicly accessible.
- Security groups restrict API tasks to the ALB, and database/cache ingress to ECS tasks.
- ALB ingress is limited to CloudFront origin-facing managed prefix list addresses.
- CloudFront uses private S3 origin access control; the frontend bucket blocks public access.
- AWS WAF managed common, known-bad-input and IP reputation rule groups, plus per-IP rate limiting.
- RDS storage encryption, AWS-managed master credentials and automated backups.
- ElastiCache encryption at rest and in transit; network access restricted to ECS. Redis has no password ACL in this baseline, so retain the private security-group boundary and add an ElastiCache ACL/user group before handling sensitive production workloads if your security policy requires authenticated Redis clients.
- Secrets Manager for runtime application secrets; no application keys in container images or source control.
- ECR image scan on push and immutable image tags.
- CloudWatch log retention and CPU/ALB error alarms. Subscribe an operations email to the SNS topic shown by `tofu output -raw alerts_topic_arn` in each environment.
- GitLab OIDC roles instead of long-lived AWS credentials.
- Production RDS deletion protection and final snapshot.

Additional production controls still required before onboarding personal data: application authentication and seller-level authorisation, secure Microsoft token persistence, audit logging, data-retention/deletion workflows, GDPR lawful-basis and outreach controls, dependency/image vulnerability scanning, and a tested restore procedure. Infrastructure IAM is not a substitute for application-level access control.

## 11. Useful commands

```bash
# Show deployed endpoints
cd infra/env/dev
tofu output

# Inspect ECS services
aws ecs list-services --cluster thinksmart-lone2stateai-dev --region eu-west-1

# Follow API logs
aws logs tail /ecs/thinksmart-lone2stateai-dev/api --follow --region eu-west-1

# Follow worker logs
aws logs tail /ecs/thinksmart-lone2stateai-dev/worker --follow --region eu-west-1

# Force a new deployment after a manual secret rotation
aws ecs update-service --cluster thinksmart-lone2stateai-dev --service api --force-new-deployment --region eu-west-1
aws ecs update-service --cluster thinksmart-lone2stateai-dev --service worker --force-new-deployment --region eu-west-1
```

Do not run `tofu destroy` against production as a routine operation. Production RDS deletion protection is enabled and the final snapshot is retained. Treat the state bucket and its version history as critical recovery assets.

## 12. Cost notes

This is a production-oriented baseline, not a free-tier design. NAT gateways, Multi-AZ RDS, ElastiCache, ALB, CloudFront/WAF, ECS tasks and backups all incur ongoing charges. Production has two NAT gateways and Multi-AZ RDS by design. Use AWS Cost Explorer and budgets before applying; development can be scheduled down outside business hours, but the NAT gateways, RDS and Redis resources continue to cost money until stopped or removed.


## Application authentication (added)

The API now uses per-user authentication. It no longer accepts the shared `X-Admin-Key`. Set `BOOTSTRAP_ADMIN_EMAIL_DEV` and `BOOTSTRAP_ADMIN_PASSWORD_DEV` as protected/masked GitLab variables for the first DEV deployment, and equivalent `_PROD` variables for the first PROD deployment. Bootstrap passwords must be at least 16 characters and include uppercase, lowercase and numeric characters. The pipeline writes these values to the environment's Secrets Manager application secret; the API creates the first admin on startup. Once the admin account has been created and verified, remove the bootstrap variables from GitLab and clear the corresponding JSON keys in Secrets Manager (keep the keys with empty values because ECS references them).

After signing in, create the five sellers in the admin dashboard. Temporary passwords are returned once and must be delivered through a secure channel; each seller must change the password at first login. Sellers can access only their assigned leads, own follow-ups and own drafts. Administrators can manage accounts and assignments.

The API container runs `alembic upgrade head` before Uvicorn. Back up the database and deploy to DEV before PROD. Access JWTs expire after 15 minutes; rotating refresh tokens are held in HttpOnly cookies. `FRONTEND_ORIGIN` must exactly match the browser origin. Keep CloudFront and API same-site; production refresh cookies are Secure, HttpOnly and SameSite=Strict.
