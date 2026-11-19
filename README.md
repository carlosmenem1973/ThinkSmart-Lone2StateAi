# ThinkSmart-Lone2StateAi

AI-assisted real-estate lead research and seller CRM for Portugal. The application includes FastAPI, PostgreSQL, Redis/Celery, Amazon Bedrock Nova and AgentCore Web Search, individual authentication, role-scoped lead CRUD, human-approved outreach drafts, follow-up records and a React dashboard.

## Important implementation boundary

This is a runnable MVP foundation, not a finished compliant production CRM. Microsoft Graph configuration scaffolding is present, but per-seller OAuth, encrypted token persistence and mailbox synchronisation are **not implemented yet**. Do not grant tenant-wide application mail permissions for this MVP. The Google Maps/Places and property-portal connectors are extension points; no scraping, CAPTCHA bypass, paywall bypass or unauthorised collection is included. Web search output is a research report and is not automatically converted into verified owner leads. Human review is required.

Authentication is now implemented in the application: individual email/password accounts, Argon2id password hashing, short-lived JWT access tokens, rotating opaque refresh tokens in HttpOnly cookies, role-based admin/seller access, seller-scoped lead/follow-up visibility, first-login password change, login lockout, session revocation and audit events. The bootstrap admin is created from environment variables on first startup. The old shared `X-Admin-Key` mechanism has been removed. Workspace branding is editable by an administrator from the dashboard: product name, customer name, tagline, logo URL and primary/accent colours. Defaults are `ThinkSmart AI | Loft2 Real Estate`; changes persist in PostgreSQL and do not require a rebuild or redeployment.

## Requirements
- Ubuntu Server 24.04 LTS or Docker Desktop for local development
- Docker Engine + Docker Compose plugin
- AWS account, domain (optional), and a GitLab project/runner for the AWS deployment
- AWS IAM permissions for Amazon Bedrock Nova Lite and AgentCore Web Search
- Microsoft Entra app registration for delegated OAuth

## Quick start (development / initial test)
```bash
cp .env.example .env
# Edit .env. Generate strong secrets:
openssl rand -hex 32
# Set POSTGRES_PASSWORD, REDIS_PASSWORD and SECRET_KEY
# Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD (minimum 16 chars)
# Set FRONTEND_ORIGIN=http://localhost:5173 and COOKIE_SECURE=false for local HTTP development
# Set Microsoft values only when configuring Entra.
docker compose up -d --build
docker compose ps
docker compose logs -f api
```
Open `http://localhost` for the local Docker Compose dashboard. Local API docs: `http://localhost/api/v1/docs`. The API is also bound to `127.0.0.1:8000` for local testing. In AWS production, API documentation is disabled by default.

Sign in using `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD`. The access token stays in browser memory; the rotating refresh token is held in a Secure/HttpOnly/SameSite cookie in production. Do not put access or refresh tokens in localStorage.

## Ubuntu server preparation
```bash
sudo apt update && sudo apt -y upgrade
sudo apt install -y ca-certificates curl git ufw
# Install Docker Engine and Compose plugin using the official Docker Ubuntu instructions.
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## HTTPS
The included Nginx configuration is an HTTP reverse proxy starter. For production, configure Let's Encrypt using Certbot (or put the service behind a managed TLS proxy), mount certificates, and add a 443 server block with `ssl_certificate` and `ssl_certificate_key`. Do not expose the API over plain HTTP to the public internet.

## Microsoft 365 setup
Microsoft mailbox synchronisation is not enabled in this release. When implementing it, create an Entra app registration, use delegated `User.Read` and `Mail.Read` scopes, bind OAuth state to the signed-in seller, and persist each seller's MSAL token cache encrypted. Do not grant tenant-wide application `Mail.Read` permissions without a separate security and mailbox-scoping review.

## Amazon Bedrock and AgentCore
The application uses the Amazon Bedrock Converse API with the EU inference profile `eu.amazon.nova-lite-v1:0` and Amazon Bedrock AgentCore Web Search (`web-search.v1`) in `eu-west-1`. The ECS task role authenticates through its standard AWS credentials; no OpenAI API key or third-party search key is required. AgentCore search results include source URLs and extracts; preserve and display source links in reports. Configure the scoped IAM permissions in `backend/thinksmart-bedrock-policy.json` (also provisioned by OpenTofu for ECS tasks).

## API endpoints
All business endpoints require `Authorization: Bearer <access_token>`. The refresh and logout endpoints use the HttpOnly refresh cookie plus same-origin validation. Public endpoints are limited to health and login.
- `GET /api/v1/health`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/change-password`
- `GET /api/v1/auth/users` (admin)
- `POST /api/v1/auth/users` (admin; creates seller/admin and returns a one-time temporary password)
- `POST /api/v1/auth/users/{id}/reset-password` (admin)
- `PATCH /api/v1/auth/users/{id}/active` (admin)
- `GET /api/v1/settings/branding` (public, read-only brand metadata for login screen)
- `PUT /api/v1/settings/branding` (admin only; persists workspace branding)
- `GET /api/v1/dashboard`
- `GET /api/v1/leads`
- `POST /api/v1/leads`
- `PATCH /api/v1/leads/{id}`
- `POST /api/v1/research?query=...&source=web|internal`
- `POST /api/v1/agents/{agent_id}/run` (six specialist agents; authenticated)
- `POST /api/v1/leads/{id}/draft`
- `POST /api/v1/drafts/{id}/approve`
- `POST /api/v1/leads/{id}/followups`
- `GET /api/v1/followups`
- `GET /api/v1/integrations/microsoft/status`

Example login:
```bash
curl -i -c cookies.txt -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@yourcompany.pt","password":"YOUR_BOOTSTRAP_PASSWORD"}'
```
The JSON response contains a short-lived access token. Use it as `Authorization: Bearer <access_token>` for API requests. Browser clients should use `credentials: include` so the HttpOnly refresh cookie is sent automatically. For refresh/logout, send the configured frontend `Origin` header when using a non-browser client.

## Roadmap before production
1. Add MFA or Microsoft Entra SSO, then extend the existing seller RBAC and audit controls.
2. Per-seller delegated Microsoft Graph mailbox connection, encrypted token cache, delta sync and message minimisation.
3. Portal connectors only through official APIs, partner feeds, licensed data or permitted public pages; respect terms, robots directives and rate limits.
4. Google Places integration with required attribution and storage/refresh rules; retain place IDs and only permitted fields.
5. Lead deduplication, source evidence records, owner verification and confidence calibration.
6. Seller territory rules, assignment, tasks, notifications, calendar integration and dashboard analytics.
7. Human-reviewed drafts, consent/lawful-basis checks, objection/suppression list, retention/deletion workflows and DPIA/legal review.
8. Automated tests, migrations, backups with restore drills, monitoring, alerting, secrets manager and vulnerability scanning.

## Portugal privacy and outreach
Public availability of a personal email or phone number is not itself permission to send marketing. Establish the legal basis and channel-specific requirements before any outreach. Include objection/suppression handling, transparency, source records, data minimisation and retention limits. Have Portuguese privacy counsel review the intended process (GDPR, Law 41/2004, CNPD guidance and applicable real-estate rules).

## Seed the five seller records
After the database is running, from the project directory:
```bash
docker compose exec api python -c "print('Use scripts/seed_sellers.py from a one-off backend container or run it in the backend Python environment')"
# On the host, with backend dependencies installed:
python -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
python scripts/seed_sellers.py
```
The five email addresses and territories in `scripts/seed_sellers.py` are placeholders. Prefer creating seller accounts from the administrator dashboard so each seller receives a one-time temporary password and is required to change it. The legacy seed script creates records without passwords and should only be used for test data. Do not onboard real email contents until encrypted per-seller Microsoft token storage and mailbox access controls are implemented.

## Workspace branding
The default dashboard identity is **ThinkSmart AI | Loft2 Real Estate**. An administrator can change the product name, customer name, tagline, logo URL and primary/accent colours in the **Identidade visual** panel. Branding is stored in the singleton `brand_settings` PostgreSQL table and is loaded on the login screen as well as the authenticated dashboard. The update endpoint is admin-only; the public GET endpoint exposes only non-sensitive display metadata. Changes apply immediately without rebuilding the frontend.

## Authentication and account administration

### Security design
- Passwords are hashed with Argon2id via `pwdlib`; plaintext passwords are never stored.
- Access JWTs expire after 15 minutes by default. The browser keeps them in memory only.
- Refresh tokens are random opaque values, stored only as SHA-256 hashes in `refresh_sessions`, rotated on every refresh and delivered in an HttpOnly cookie.
- Production cookies use `Secure`, `HttpOnly`, `SameSite=Strict`, and the `/api/v1/auth` path. Refresh and logout require an exact `Origin` match with `FRONTEND_ORIGIN`.
- Five failed logins temporarily lock an account for 15 minutes. Deactivated users cannot authenticate; deactivation revokes refresh sessions.
- Admins can create accounts, deactivate accounts and reset passwords. New users must change the temporary password at first sign-in.
- Sellers can view and update only leads assigned to them; their follow-ups and drafts are scoped to their account. Only admins can assign leads or change outreach authorisation/lawful-basis fields.
- Audit events are recorded for authentication, user administration, lead changes and outreach draft approval.

### First administrator
Set `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` (at least 16 characters with uppercase, lowercase and digits) for the first production deployment. On startup the API creates the administrator only if no usable administrator exists. After the first successful bootstrap, remove these values from GitLab CI/CD variables and set the matching Secrets Manager JSON keys to empty strings; the application retains the administrator account and does not need the bootstrap password again.

For Docker Compose, set the two variables in `.env`. For AWS, set `BOOTSTRAP_ADMIN_EMAIL_DEV` / `BOOTSTRAP_ADMIN_PASSWORD_DEV` and their `_PROD` counterparts as protected/masked GitLab variables for initial provisioning only. The Secrets Manager keys must remain present (empty is acceptable after bootstrap) because the ECS task definition references them.

### Create the five sellers
Sign in as admin and use the **Contas da equipa** panel to create each seller. A temporary password is shown once; deliver it through a secure channel. The seller must change it at first login. You can also use `POST /api/v1/auth/users` with an admin access token. Do not use placeholder accounts for real people.

### Database migration
The API container runs `alembic upgrade head` before starting Uvicorn. The migration is idempotent for the original MVP database and creates the authentication columns and refresh-session table. Back up RDS before the first production deployment and verify the migration in DEV first.

### Operational notes
- Configure `FRONTEND_ORIGIN` to the exact browser origin (scheme + host, no trailing path).
- Set `COOKIE_SECURE=true` in any HTTPS deployment; production defaults to secure cookies. Local HTTP development can use `COOKIE_SECURE=false`.
- Keep `SECRET_KEY` stable and unique per environment, at least 32 random characters. Rotating it invalidates all access tokens.
- The current refresh endpoint uses SameSite=Strict plus exact Origin checking; keep the frontend and API same-site behind CloudFront.
- This is application password authentication, not Microsoft Entra SSO. Microsoft mailbox OAuth is a separate delegated integration and remains disabled for sync until per-user state binding and encrypted token-cache persistence are implemented.
- Add MFA/Entra SSO and a formal password-reset delivery process before broad external rollout.

## AWS deployment (OpenTofu)

The AWS implementation for separate Development and Production environments is in `infra/` and `scripts/aws/`. It provisions ECS Fargate, ECR, RDS PostgreSQL, ElastiCache Redis, private networking, CloudFront/S3, AWS WAF, Secrets Manager, CloudWatch and GitLab OIDC deployment roles.

Workspace branding can be changed by an administrator at runtime; see [Branding settings](docs/branding-settings.md). Start with [the AWS deployment guide](docs/aws-deployment.md). The initial OpenTofu apply intentionally creates ECS services with desired count zero; the GitLab pipeline then builds/pushes images, populates Secrets Manager, and starts the services.

The GitLab pipeline is `.gitlab-ci.yml`. Development deploys automatically from `main`; production is a manual protected deployment. Configure the required GitLab CI/CD variables in the deployment guide before enabling either environment.
"# ThinkSmart-Lone2StateAi" 
