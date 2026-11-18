# ThinkSmart AI — Cognito-only authentication / RBAC refactor

## What changed
- `app.core.auth.get_current_user()` validates Cognito access JWTs (RS256, issuer, token_use=access, client_id) and reads `cognito:groups`. It does not inject or query a PostgreSQL session.
- `GET /api/v1/auth/me` returns Cognito identity and groups without PostgreSQL.
- `get_business_user()` lazily resolves/creates the legacy PostgreSQL business profile only for endpoints that need relational ownership/audit records. This is not part of authentication. If RDS is unavailable, `/auth/me` remains usable; data operations naturally still require RDS.
- Role mapping: SUPER_ADMIN > ADMIN > MANAGER > SELLER > VIEWER.
- VIEWER is read-only for write operations.
- MANAGER currently receives seller-level lead scope (own assigned leads only). The supplied schema has no team-membership relation, so granting cross-seller visibility would be unsafe until that relation is designed.
- Admin user creation assigns the matching Cognito group.
- Existing business tables and foreign keys are retained.
- Legacy local password/bootstrap is disabled.

## Cognito groups
Create these groups in the existing pool `eu-west-1_BZKyKZ2Uk` (do not create a new pool):
```powershell
$pool = "eu-west-1_BZKyKZ2Uk"
$region = "eu-west-1"
$groups = @("SUPER_ADMIN","ADMIN","MANAGER","SELLER","VIEWER")
foreach ($group in $groups) {
  aws cognito-idp create-group --region $region --user-pool-id $pool --group-name $group 2>$null
}
```
The command may report `GroupExistsException` for groups already present; that is harmless.
Assign existing identities (only after confirming their ownership):
```powershell
aws cognito-idp admin-add-user-to-group --region eu-west-1 --user-pool-id eu-west-1_BZKyKZ2Uk --username management@thinksmart.pt --group-name ADMIN
aws cognito-idp admin-add-user-to-group --region eu-west-1 --user-pool-id eu-west-1_BZKyKZ2Uk --username info@thinksmart.pt --group-name SELLER
```
Cognito username may be the UUID returned by AdminGetUser if email is not the sign-in alias. Use the exact `Username` returned by `admin-get-user`.

## ECS task role IAM permissions
The backend uses AdminGetUser for profile attributes when Cognito access tokens do not contain email/name, and AdminAddUserToGroup when an administrator creates a user. Add this least-privilege statement to the existing ECS TASK ROLE policy (not execution role), retaining other existing permissions:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "ThinkSmartCognitoProfileAndGroups",
    "Effect": "Allow",
    "Action": [
      "cognito-idp:AdminGetUser",
      "cognito-idp:AdminAddUserToGroup"
    ],
    "Resource": "arn:aws:cognito-idp:eu-west-1:049451987829:userpool/eu-west-1_BZKyKZ2Uk"
  }]
}
```
If your existing user-management endpoints use AdminCreateUser/AdminResetUserPassword/AdminEnableUser/AdminDisableUser, retain their current permissions too.

## Database migration
The new migration adds the additional PostgreSQL enum labels and does not delete or rewrite business data:
```powershell
alembic upgrade head
```
Run this as a one-off ECS task using the production task definition/network/secrets, not from a Windows workstation outside the VPC. Do not update the ECS service until the migration and smoke tests succeed.

## Required ECS environment
- `AWS_REGION=eu-west-1`
- `COGNITO_USER_POOL_ID=eu-west-1_BZKyKZ2Uk`
- `COGNITO_APP_CLIENT_ID=6u2tfv98ro8bbkrub6bn2oarto`

Keep existing DATABASE_URL/SECRET_KEY secret references unchanged.

## Frontend contract
`GET /api/v1/auth/me` now returns:
```json
{
  "id": "<Cognito sub>",
  "sub": "<Cognito sub>",
  "email": "user@example.com",
  "full_name": "User Name",
  "role": "admin",
  "groups": ["ADMIN"],
  "active": true,
  "must_change_password": false,
  "territory": null
}
```
Frontend role type must allow `super_admin | admin | manager | seller | viewer`, and menu guards should use `groups` or normalized role. Keep Amplify Cognito sign-in and pass the **access token** as Bearer token.

## Validation
- `python -m compileall app scripts`
- `GET /health/live` returns 200.
- Cognito sign-in succeeds.
- `GET /api/v1/auth/me` succeeds even when the API has no database connection (auth dependency has no DB dependency).
- An authenticated user without one of the five groups receives 403.
- Viewer can read permitted resources but receives 403 on write endpoints.
- A seller can only access their assigned leads.
- Admin/manager data operations use PostgreSQL and therefore still require RDS connectivity.

## Important scope
This package preserves the existing schema and business relations. PostgreSQL is no longer an authentication gate, but remains required for business data operations, lead ownership, follow-ups, drafts and audit. No AWS resource is changed by building this package.
