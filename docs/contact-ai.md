# Contact AI — website chat

Contact AI adds an embeddable website chat backed by Amazon Bedrock Nova Lite in `eu-west-1`, PostgreSQL conversation history, Cognito-protected administration, and a Celery Beat review cycle every 30 minutes.

## Embed the chat

After deploying the frontend static assets, add this script to the public website immediately before `</body>`:

```html
<script
  src="https://webportal.thinksmart.pt/contact-ai-widget.js"
  data-api="https://YOUR_API_DOMAIN/api/v1"
  defer
></script>
```

Replace `YOUR_API_DOMAIN` with the existing ThinkSmart API hostname. If the public website is served by the same CloudFront distribution and API path, use `data-api="/api/v1"`.

The widget sends visitor messages to `POST /api/v1/contact-ai/chat`. The endpoint is public by design; configure API Gateway/WAF or the existing ALB/WAF rate controls before production exposure. Restrict CORS to the exact public website origin(s).

## Administration

The authenticated admin panel is available under **Contact AI**.

- Activate/deactivate: `PUT /api/v1/contact-ai/settings`
- Pause: `POST /api/v1/contact-ai/pause`
- Resume: `POST /api/v1/contact-ai/resume`
- Remove configuration: `DELETE /api/v1/contact-ai/configuration`
- View recent conversations: `GET /api/v1/contact-ai/conversations`
- View conversation messages: `GET /api/v1/contact-ai/conversations/{id}/messages`

Initial configuration is disabled, mode `approval`, channel `website`, interval 30 minutes. An administrator must explicitly activate it.

## Modes and the 30-minute cycle

- **Approval:** Nova Lite prepares an internal draft; the visitor receives a neutral acknowledgement.
- **Autonomous:** Nova Lite replies during the active website chat. The 30-minute worker reviews recent conversations only when the visitor explicitly opted in to follow-up, and creates an internal suggestion. It does not push messages to an offline visitor.
- The cycle is registered in Celery Beat at 1,800 seconds. The ECS worker must run Celery Beat (the current worker command uses `--beat`).

The website channel is interactive only while the visitor is on the website. To proactively message an offline visitor, a separately authorized channel (for example email or WhatsApp Business) and its consent/opt-in workflow would be required; neither is enabled by this implementation.

## Database migration and deployment

Run the normal release migration before deploying the API:

```bash
cd backend
alembic upgrade head
```

Then build and deploy the API, worker and frontend assets together. Verify the worker logs show the `contact-ai-every-30-minutes` Beat schedule and verify the admin status endpoint. No AWS resources are provisioned or deployed by this source change.

## Privacy and safeguards

- The website widget includes an explicit opt-in checkbox for follow-up. No consent is inferred from a chat message.
- Conversation access requires Cognito authentication; viewer accounts cannot read conversations.
- Public chat stores visitor messages and optional contact details in RDS.
- Do not collect sensitive personal data in the chat. Add an approved privacy notice, retention policy, data-subject request handling, anti-abuse/rate limiting and monitoring before production launch.
- The autonomous mode only automates the live website response; it does not send email, SMS, WhatsApp, or off-session messages.
