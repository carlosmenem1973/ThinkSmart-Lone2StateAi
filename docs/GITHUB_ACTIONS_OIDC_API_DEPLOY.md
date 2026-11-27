# GitHub Actions OIDC — Production API deployment

This configuration is intentionally limited to the existing production API.
It does not deploy the frontend, Worker, Beat, SQS, Redis, or provision infrastructure.

## Confirmed production resource identifiers

- AWS account: `049451987829`
- Region: `eu-west-1`
- ECS cluster: `thinksmart-cluster`
- ECS service: `thinksmart-api`
- ECR repository: `thinksmart-api`
- ECS task role: `arn:aws:iam::049451987829:role/thinksmart-ecs-task-role`
- ECS execution role: `arn:aws:iam::049451987829:role/thinksmart-ecs-execution-role`

The workflow expects these GitHub Environment variables in the `production` environment:

| Variable | Value |
|---|---|
| `AWS_REGION` | `eu-west-1` |
| `AWS_ACCOUNT_ID` | `049451987829` |
| `AWS_ROLE_ARN` | ARN of `thinksmart-github-actions-prod-role` |
| `ECR_REPOSITORY_NAME` | `thinksmart-api` |
| `ECS_CLUSTER_NAME` | `thinksmart-cluster` |
| `ECS_API_SERVICE_NAME` | `thinksmart-api` |
| `ECS_API_CONTAINER_NAME` | `thinksmart-api` |

## OIDC provider

Issuer: `https://token.actions.githubusercontent.com`

Audience: `sts.amazonaws.com`

Expected provider ARN:
`arn:aws:iam::049451987829:oidc-provider/token.actions.githubusercontent.com`

The provider did not exist in the last read-only AWS inventory. Create it only after verifying the current AWS/GitHub OIDC thumbprint requirements.

## Trust policy for thinksmart-github-actions-prod-role

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOnlyThinkSmartProductionEnvironment",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::049451987829:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:carlosmenem1973/ThinkSmart-Lone2StateAi:environment:production"
        }
      }
    }
  ]
}
```

Restrict the GitHub `production` Environment to branch `main` and require approval where available. Because the workflow uses a GitHub Environment, the OIDC subject identifies the environment, not the branch.

## Permissions policy for thinksmart-github-actions-prod-role

This policy allows pushing an image to the existing API ECR repository, registering a new revision of the existing API task-definition family, running the migration task, and updating only the existing API ECS service.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EcrLogin",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "PushOnlyThinkSmartApiImage",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchGetImage",
        "ecr:CompleteLayerUpload",
        "ecr:DescribeRepositories",
        "ecr:InitiateLayerUpload",
        "ecr:PutImage",
        "ecr:UploadLayerPart"
      ],
      "Resource": "arn:aws:ecr:eu-west-1:049451987829:repository/thinksmart-api"
    },
    {
      "Sid": "ReadOnlyApiEcsResources",
      "Effect": "Allow",
      "Action": [
        "ecs:DescribeClusters"
      ],
      "Resource": "arn:aws:ecs:eu-west-1:049451987829:cluster/thinksmart-cluster"
    },
    {
      "Sid": "DescribeOnlyApiService",
      "Effect": "Allow",
      "Action": [
        "ecs:DescribeServices"
      ],
      "Resource": "arn:aws:ecs:eu-west-1:049451987829:service/thinksmart-cluster/thinksmart-api"
    },
    {
      "Sid": "ManageOnlyApiTaskDefinitionFamily",
      "Effect": "Allow",
      "Action": [
        "ecs:RegisterTaskDefinition"
      ],
      "Resource": "arn:aws:ecs:eu-west-1:049451987829:task-definition/thinksmart-api:*"
    },
    {
      "Sid": "DescribeTaskDefinitions",
      "Effect": "Allow",
      "Action": "ecs:DescribeTaskDefinition",
      "Resource": "*"
    },
    {
      "Sid": "RunApiMigrationTasksOnlyInThinkSmartCluster",
      "Effect": "Allow",
      "Action": [
        "ecs:RunTask"
      ],
      "Resource": "arn:aws:ecs:eu-west-1:049451987829:task-definition/thinksmart-api:*",
      "Condition": {
        "ArnEquals": {
          "ecs:cluster": "arn:aws:ecs:eu-west-1:049451987829:cluster/thinksmart-cluster"
        }
      }
    },
    {
      "Sid": "DescribeTasksInThinkSmartCluster",
      "Effect": "Allow",
      "Action": [
        "ecs:DescribeTasks"
      ],
      "Resource": "arn:aws:ecs:eu-west-1:049451987829:task/thinksmart-cluster/*"
    },
    {
      "Sid": "UpdateOnlyThinkSmartApiService",
      "Effect": "Allow",
      "Action": [
        "ecs:UpdateService"
      ],
      "Resource": "arn:aws:ecs:eu-west-1:049451987829:service/thinksmart-cluster/thinksmart-api"
    },
    {
      "Sid": "PassOnlyExistingEcsTaskRoles",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": [
        "arn:aws:iam::049451987829:role/thinksmart-ecs-task-role",
        "arn:aws:iam::049451987829:role/thinksmart-ecs-execution-role"
      ],
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": "ecs-tasks.amazonaws.com"
        }
      }
    }
  ]
}
```

No permission is granted to create or modify IAM roles, policies, OIDC providers, ECS clusters, networking, RDS, ElastiCache, SQS, Secrets Manager values, S3, or CloudFront. The role can update only the existing `thinksmart-api` service; it cannot create or delete ECS services. ECS `DescribeTaskDefinition` requires `Resource: "*"` in the current service authorization model; all ECS write actions remain scoped to the API task-definition family, API service, and target cluster. ECR `BatchGetImage` is included because Docker image push requires it per AWS documentation.

## Deployment behavior

1. Requires a manual workflow dispatch from `main` and the exact confirmation `DEPLOY-PRODUCTION`.
2. Assumes the role through GitHub OIDC.
3. Pushes a commit/run-specific immutable image tag to `thinksmart-api`.
4. Copies the existing API task definition, changing only the API container image.
5. Runs `alembic upgrade head` as a one-off Fargate task using the API service's current network configuration.
6. Updates only `thinksmart-api` and waits for the service to become stable.

The deployment script does not read or update Secrets Manager values. Existing ECS secret references and task/execution roles are preserved. The existing omnichannel deployment script remains separate and is not invoked by this workflow.

## Operational caution

Database migrations are production changes. Review the migration chain and backup posture before approving a production run. The workflow is not automatically triggered by pushes or pull requests.
