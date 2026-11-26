# GitHub Actions AWS deployment

The workflow `.github/workflows/deploy-aws.yml` deploys the existing OpenTofu-managed DEV or PROD environment to AWS. It is started manually from GitHub Actions and uses GitHub OIDC; no long-lived AWS access keys are stored in GitHub.

## Important: existing infrastructure is required

This workflow is for routine deployments of environments that have already been bootstrapped with the OpenTofu state described in [aws-deployment.md](aws-deployment.md). It deliberately does **not** run the initial zero-task bootstrap apply: that bootstrap would scale existing ECS services down during a routine deployment. If the remote state or ECR repositories do not exist, the workflow fails during its state preflight instead of creating a second environment.

The workflow still applies the existing OpenTofu configuration after building the image, just as the current GitLab pipeline does. Review infrastructure changes before enabling Production.

## 1. Create the GitHub OIDC provider in AWS

In AWS IAM, create an OpenID Connect provider if one does not already exist:

- Provider URL: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`

AWS account: `049451987829`. Provider ARN:

```text
arn:aws:iam::049451987829:oidc-provider/token.actions.githubusercontent.com
```

Do not create a duplicate provider if it already exists.

## 2. Create one deployment role per GitHub Environment

Create separate IAM roles for DEV and PROD. Their trust policies must restrict access to this repository and the corresponding GitHub Environment. Example DEV trust policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::049451987829:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:carlosmenem1973/ThinkSmart-Lone2StateAi:environment:dev"
        }
      }
    }
  ]
}
```

For PROD, create a separate role and change the subject to:

```text
repo:carlosmenem1973/ThinkSmart-Lone2StateAi:environment:prod
```

The workflow's OpenTofu deployment role needs the same infrastructure permissions as the existing environment-specific GitLab deployment role: `PowerUserAccess` plus the project's constrained IAM provisioning/PassRole policy. Do not attach unrestricted AdministratorAccess. The existing policy is defined in `infra/modules/platform/main.tf` under `aws_iam_role_policy.gitlab_iam_limited`; review it and reproduce the required permissions for the GitHub role. Keep DEV and PROD roles separate.

Save each role ARN as an environment secret named `AWS_ROLE_ARN` in its matching GitHub Environment.

## 3. Configure GitHub Environments

In **Settings → Environments**, create environments named exactly:

- `dev`
- `prod`

For `prod`, configure required reviewers and prevent self-review if your GitHub plan/settings support it. This ensures the Production deployment waits for approval.

## 4. Configure environment variables and secrets

Configure the following separately in each GitHub Environment. Use the same variable names in both environments; the values differ by environment.

**Environment variables**

| Name | Purpose |
|---|---|
| `TF_STATE_BUCKET` | Existing encrypted/versioned OpenTofu S3 state bucket |
| `AWS_ACCOUNT_ID` | `049451987829` |
| `GITLAB_OIDC_PROVIDER_ARN` | Existing GitLab OIDC provider ARN, retained temporarily so this deployment does not remove the existing GitLab CI role from Terraform state |
| `GITLAB_OIDC_SUBJECT` | Existing exact GitLab subject for the protected main branch |
| `MICROSOFT_TENANT_ID` | Entra tenant ID, or `common` while tenant configuration is pending |
| `ALB_CERTIFICATE_ARN` | Optional ACM certificate ARN for the API origin |
| `API_ORIGIN_DOMAIN_NAME` | Optional API origin hostname covered by the certificate |
| `ROUTE53_ZONE_ID` | Optional Route 53 hosted-zone ID |

**Environment secrets**

| Name | Purpose |
|---|---|
| `AWS_ROLE_ARN` | GitHub OIDC deployment role ARN for this environment |
| `SECRET_KEY` | Unique random application signing secret for this environment |
| `BOOTSTRAP_ADMIN_EMAIL` | Initial administrator email; clear after bootstrap |
| `BOOTSTRAP_ADMIN_PASSWORD` | Initial administrator password (minimum 16 characters); clear after bootstrap |
| `MICROSOFT_CLIENT_ID` | Entra application client ID |
| `MICROSOFT_CLIENT_SECRET` | Entra application client secret |
| `GOOGLE_MAPS_API_KEY` | Optional Google Maps API key |

Use separate DEV and PROD application secrets. Never put secret values in repository variables, workflow YAML or source control.

The two GitLab OIDC variables are transitional: the current OpenTofu module still manages the GitLab CI role. Keep their existing values in GitHub Environment variables while this workflow uses the current module. A later infrastructure change can migrate that role's trust and outputs fully to GitHub OIDC.

## 5. Run a deployment

1. Merge the workflow into `main`.
2. Open **Actions → ThinkSmart AWS Deployment → Run workflow**.
3. Select `dev) for the first deployment.
4. Wait for validation, image publication, OpenTofu apply, frontend publication and ECS stability checks.
5. Verify the DEV application and API before starting another run with `prod`.
6. PROD waits for the configured GitHub Environment approval.

The workflow builds one backend image and pushes it to both API and worker ECR repositories, updates the Secrets Manager application secret, applies the image tag and desired ECS counts (DEV: one API and one worker; PROD: two API and one worker), syncs the frontend to S3, invalidates CloudFront and waits for ECS services to become stable.

## 6. First-run and safety notes

- The remote OpenTofu state and AWS infrastructure must already exist. Do not use this routine deployment workflow as the initial infrastructure bootstrap.
- The workflow uses the existing `scripts/aws/set-runtime-secrets.sh` helper and the existing OpenTofu outputs.
- The API container runs `alembic upgrade head` before Uvicorn according to the repository's deployment design. Take/verify an RDS backup and validate migrations in DEV before PROD.
- Do not select PROD until DEV has been checked, including `GET /api/v1/ai/status`, `GET /api/v1/agents`, login and the frontend.
- The workflow does not automatically trigger on every push. This is intentional: deployments are explicit via `workflow_dispatch`.
