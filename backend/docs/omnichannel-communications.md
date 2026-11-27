# ThinkSmart AI — Omnichannel Communications

## Product decisions
- One central business account owns WhatsApp and outbound email. WhatsApp uses Meta Cloud API; outbound email uses Amazon SES so it does not require Microsoft 365 tenant admin consent. Microsoft Graph remains an optional integration for mailbox access, not the outbound sender in this increment.
- Hybrid autonomy: inbound requests can be interpreted and a response draft prepared; outbound communication remains subject to human approval.
- Voice is out of scope for this increment.
- Customers and property owners are represented by CRM contacts, with contact_type set to client or owner.

## Implemented API foundation
- Central channel registry for Meta WhatsApp Cloud API, AWS SES outbound email, AWS End User Messaging and Microsoft Graph.
- Per-contact, per-channel, per-purpose consent records with evidence and revocation timestamps.
- Unified communication threads linked to CRM contacts and optional leads.
- Message history model with provider IDs and delivery states.
- Webhook event idempotency ledger.
- Authenticated inbox, consent management, outbound draft creation and administrator approval audit.
- CRM matching between client contacts and property-discovery leads.
- Specialist-agent CRM context for lead-qualifier, follow-up-assistant and owner-intelligence.
- Meta WhatsApp webhook verification and inbound text/button/interactive message persistence.
- For known CRM contacts, Bedrock prepares a CRM-grounded WhatsApp reply draft for human approval. It does not send it.
- do_not_contact and explicit channel/purpose withdrawals are respected before generating a reply draft.

All routes are under /api/v1:
- GET /communications/overview
- POST /communications/channels (administrator)
- PUT /communications/channels/{channel_id}/inbound (administrator; enable/disable inbound webhook)
- PUT and GET /communications/contacts/{contact_id}/consent
- POST /communications/drafts
- GET /communications/inbox
- GET /communications/inbox/{thread_id}/messages
- PUT /communications/channels/{channel_id}/outbound (administrator; enable/disable verified outbound provider)
- POST /communications/drafts/{message_id}/approve (administrator; validates consent and dispatches through the configured provider)
- GET /webhooks/meta/whatsapp (Meta subscription verification)
- POST /webhooks/meta/whatsapp (signed inbound webhook)

## Meta WhatsApp Cloud API setup

### Secrets and environment
Configure these environment variables from AWS Secrets Manager in the ECS API task. Never commit the values or place credentials in `configuration_json`:
- `META_WHATSAPP_VERIFY_TOKEN`: a long random value chosen by the operator and entered in Meta's webhook configuration.
- `META_WHATSAPP_APP_SECRET`: Meta app secret, used to verify `X-Hub-Signature-256`.
- `META_WHATSAPP_PHONE_NUMBER_ID`: the WhatsApp Business phone number ID.

The corresponding application settings are `meta_whatsapp_verify_token`, `meta_whatsapp_app_secret`, and `meta_whatsapp_phone_number_id`.

### Meta developer console
Set the callback URL to:

```
https://api.thinksmart.pt/api/v1/webhooks/meta/whatsapp
```

Enter the same `META_WHATSAPP_VERIFY_TOKEN` value and subscribe to the `messages` webhook field. Meta's GET verification challenge is returned as plain text. POST requests are accepted only with a valid HMAC SHA-256 signature and an enabled inbound channel matching the configured phone number ID.

### Register and enable inbound
First register the channel as an administrator:

```http
POST /api/v1/communications/channels
Content-Type: application/json

{
  "channel": "whatsapp",
  "provider": "meta_whatsapp_cloud",
  "display_name": "ThinkSmart WhatsApp",
  "sender_identifier": "business phone label"
}
```

Then enable inbound for the returned channel ID:

```http
PUT /api/v1/communications/channels/{channel_id}/inbound
Content-Type: application/json

{
  "phone_number_id": "META_PHONE_NUMBER_ID",
  "enabled": true
}
```

The second endpoint refuses activation unless the app secret and verify token are present in the API environment. Disabling inbound uses the same endpoint with `enabled: false`.

## Inbound processing and safety boundaries
1. Meta webhook signature and configured phone number ID are validated.
2. Each inbound message is deduplicated by the provider message ID and stored in the communications inbox.
3. The sender is linked to an active CRM contact by digit-normalised phone number (including the Portuguese `00351` format) only when the phone identifies exactly one active CRM contact. Ambiguous/duplicate phone numbers and unknown senders are stored in an unlinked thread; no CRM contact is auto-created.
4. For known clients, deterministic CRM matching ranks existing property leads using stored location, budget, property type, bedrooms, area and operation criteria.
5. For known owners, existing leads are associated only by exact email or normalised phone; this does not verify legal ownership.
6. Bedrock prepares a short response draft grounded in the CRM results. The draft is stored as `pending_approval` in the same thread. No WhatsApp message is sent.
7. Contacts with global suppression or an explicit WhatsApp service/property-enquiry withdrawal are not processed into a draft.

Unmatched senders and non-text media messages are stored for human handling. Media is not downloaded or transcribed in this increment. Delivery/read status callbacks are acknowledged but not yet persisted as delivery-state updates.

### Execution model limitation
The initial AI draft preparation uses FastAPI background tasks after webhook persistence. This is suitable as an initial integration but is not a durable queue: a process restart can interrupt processing. Before production traffic, move the processor to an SQS-backed ECS worker with retries, visibility timeout, idempotent completion, dead-letter queue and CloudWatch alarms. The API must acknowledge Meta quickly and never wait for Bedrock inference.

## Outbound delivery

Outbound dispatch is implemented for approved text messages:
- WhatsApp uses Meta WhatsApp Cloud API Graph API v26.0 and a permanent system-user access token. Free-form text is permitted only when the latest inbound message in the same thread is less than 24 hours old. Outside that window the API rejects the send; approved template support is not implemented.
- Email uses Amazon SES v2 in `AWS_REGION`, from `EMAIL_FROM_ADDRESS` (default `contacto@cbloft2.pt`). This avoids Microsoft Graph application permissions and Microsoft 365 tenant admin consent.
- The approval endpoint re-checks global suppression, channel/purpose consent and expiry immediately before dispatch. It requires an enabled outbound channel, records provider IDs, sent timestamps and audit events, and marks provider failures as failed.
- The API commits a `sending` state before calling the provider to reduce concurrent duplicate approvals. `sent` means accepted by the provider, not confirmed delivered to the recipient; delivery/read webhook persistence is not yet implemented. A process crash after provider acceptance but before the final database commit can still require manual reconciliation; a durable SQS outbox/worker is the next reliability improvement. Do not blindly retry messages in `sending`.

### AWS and Meta configuration

Inject these values from AWS Secrets Manager into the ECS API task (never commit secrets):
- `META_WHATSAPP_ACCESS_TOKEN`: permanent Meta system-user token with `whatsapp_business_messaging`.
- `META_WHATSAPP_PHONE_NUMBER_ID`: sender phone-number ID.
- `META_GRAPH_API_VERSION`: defaults to `v26.0`; pin and update deliberately.
- `EMAIL_FROM_ADDRESS=contacto@cbloft2.pt`.
- `SES_SENDER_VERIFIED=true` only after the SES identity is verified and DKIM/SPF DNS records are published.

For SES, verify `cbloft2.pt` (recommended) or the exact sender address in Amazon SES in `eu-west-1`; publish the SES DKIM records and configure a custom MAIL FROM/SPF/DMARC policy as appropriate. If the SES account is still in its sandbox, recipients must also be verified or the account must be moved to production. The application IAM task role needs `ses:SendEmail` (and no static AWS access keys).

Register outbound channels as an administrator:
```http
POST /api/v1/communications/channels
Content-Type: application/json

{"channel":"email","provider":"aws_ses","display_name":"ThinkSmart Email","sender_identifier":"contacto@cbloft2.pt"}
```
For the returned channel ID, enable outbound only after SES verification:
```http
PUT /api/v1/communications/channels/{channel_id}/outbound
Content-Type: application/json

{"enabled":true}
```
For WhatsApp, register the existing Meta channel and enable outbound with the same outbound endpoint after the permanent token and phone-number ID are present. The inbound endpoint remains separately configured.

Approving a pending draft now commits the approval and a `communication_outbox` row in one database transaction. A Celery relay publishes only the message ID to an encrypted SQS FIFO queue; the ECS Worker revalidates consent/channel state and performs provider delivery. A DLQ is configured with a five-receive redrive threshold. The consumer uses database message state and FIFO deduplication to avoid blind resend after ambiguous outcomes; such cases are marked `delivery_uncertain` for reconciliation. Provider acceptance is still not proof of delivery. Voice is not implemented.

## Database migration
The communications models and Alembic migrations `0009_communications` and `0010_communications_outbox` are part of this PR branch. Apply and validate the migration chain against disposable PostgreSQL before deploying. The outbox table stores delivery state and references the message; SQS payloads contain only the message ID, not recipient details or message content.


## Portal UI — Contact AI

The existing portal navigation is unchanged. The omnichannel workspace is embedded inside the existing **Contact AI** section; no new sidebar item or portal redesign is introduced.

The workspace provides internal tabs for:
- **Conversas**: recent communication threads.
- **WhatsApp**: threads received through the Meta inbound webhook.
- **Email**: email-channel threads (when available).
- **Aprovações**: pending response drafts requiring human review.

The frontend uses the authenticated API routes:
- `GET /api/v1/communications/inbox`
- `GET /api/v1/communications/inbox/{thread_id}/messages`
- `GET /api/v1/communications/drafts/pending`
- `POST /api/v1/communications/drafts/{message_id}/approve`

The pending-drafts endpoint is permission-scoped: sellers only see drafts assigned to their threads; administrators and managers can see workspace drafts; viewer accounts are denied. Approval is administrator-only.

The workspace uses a responsive three-column layout on wide screens:
- **Left:** thread list and channel/approval filters.
- **Center:** selected conversation and message history, with administrator-only approval controls.
- **Right:** permission-scoped CRM context for the linked contact, including contact type, email/phone, location, client budget/preferences, consent/suppression indicators, and up to eight deterministic property matches from `GET /api/v1/matching/contacts/{contact_id}/properties`.

The CRM panel resolves the linked contact through the permission-scoped contacts search and then calls the matching endpoint. Unlinked/unknown senders show no CRM profile. Owner-to-property associations are explicitly labelled as CRM matches and do not verify legal ownership. The layout collapses to two columns and then one column on smaller screens.


**Important:** approving a draft triggers provider delivery only when an administrator has enabled a verified outbound channel. The approval action durably queues the external send; verify the recipient, content and consent before approving. The UI must display `queued`, `sending`, `sent`, `failed` and `delivery_uncertain` distinctly.
