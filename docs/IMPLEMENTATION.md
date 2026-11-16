# ThinkSmart AI — Cognito + Amplify replacement files

This package is a targeted update for the uploaded source ZIP. It is not a full application export. It keeps the existing Cognito User Pool and App Client; it does not create or migrate Cognito users.

## Frontend files

Replace/add the corresponding files in the repository:

- `amplify.yml` (repository root)
- `frontend/package.json`
- `frontend/.env.example` (reference only; configure actual values in Amplify Console)
- `frontend/src/amplify.ts`
- `frontend/src/auth.ts`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/vite-env.d.ts`

The provided Amplify build uses `npm install` because the supplied project ZIP did not contain a package-lock.json. For a reproducible production build, run `npm install` in `frontend/`, commit the generated `package-lock.json`, then change the Amplify preBuild command to `npm ci`.

## Backend files

- Replace `backend/app/core/config.py`.
- Replace `backend/app/main.py`.
- Replace `backend/app/api/routes.py` (the package now disables local login and uses Cognito Admin APIs for team user creation/reset/disable).
- Add `backend/scripts/link_existing_cognito_users.py`.
- Replace `backend/app/core/auth.py`.
- Replace `backend/app/models/entities.py` with the supplied version.
- Add `backend/migrations/versions/0003_cognito_identity.py`.
- Replace `backend/requirements.txt` with the supplied version (includes PyJWT and boto3).
- Set the variables from `backend/.env.cognito.example` in the ECS task definition / Secrets Manager.

## Required database migration

Run from the backend deployment environment before switching the frontend: `alembic upgrade head`. Back up PostgreSQL first. The migration adds one nullable unique identity column and does not delete or rewrite existing users or business data.

## Link existing users

Run `PYTHONPATH=. python scripts/link_existing_cognito_users.py` from the `backend/` directory using an IAM role allowed to call `cognito-idp:ListUsers`. The script links verified Cognito email addresses to existing application rows by setting `cognito_sub`; it does not create, delete or alter users, passwords, roles, leads or assignments. Review its output and database backup before running. The backend then requires an exact `sub` match and never auto-links an identity from a request claim.

## Important backend route cleanup

The supplied replacement `routes.py` deprecates local `/auth/login`, `/auth/refresh`, `/auth/logout` and `/auth/change-password`. Cognito handles sign-in, session renewal, sign-out and password changes. Team user creation and password reset use Cognito Admin APIs. The ECS task role therefore needs `cognito-idp:AdminCreateUser`, `cognito-idp:AdminResetUserPassword`, `cognito-idp:AdminEnableUser`, and `cognito-idp:AdminDisableUser` on this exact User Pool. The one-time linking script additionally needs `cognito-idp:ListUsers`. Restrict these permissions to the backend task role and remove `ListUsers` after linking is complete.

## Verify

1. Cognito App Client allows the sign-in flow used by your existing app and email sign-in is enabled.
2. Amplify environment variables match the existing pool and app client exactly.
3. Backend issuer is `https://cognito-idp.eu-west-1.amazonaws.com/<POOL_ID>`.
4. ECS task role can reach Cognito JWKS over HTTPS; no AWS secret key is required to verify JWTs.
5. `GET /api/v1/auth/me` succeeds with `Authorization: Bearer <Cognito access token>`.
6. API CORS allows the exact Amplify domain.
7. `VITE_API_URL` points to the deployed FastAPI origin plus `/api/v1`.

## Limitation to address before production

The frontend includes the Cognito `NEW_PASSWORD_REQUIRED` first-login challenge for invited sellers. Other configured MFA challenges must be enabled in the frontend if your User Pool requires them. The current React dashboard retains its existing layout and features. This package changes authentication and user provisioning, but does not redesign every dashboard section or implement the six AI agents. The seller form now expects a Cognito invitation message rather than a temporary password; update its success text if desired.
