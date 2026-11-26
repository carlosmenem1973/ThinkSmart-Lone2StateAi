# ThinkSmart AI — Omnichannel Communications

## Product decisions
- One central business account owns WhatsApp, SMS and Microsoft 365 email channels.
- Hybrid autonomy: inbound requests can be interpreted and a response draft prepared; outbound communication remains subject to human approval.
- Voice is out of scope for this increment.
- Customers and property owners are represented by CRM contacts, with contact_type set to client or owner.

## Implemented API foundation
- Central channel registry for Meta WhatsApp Cloud API, AWS End User Messaging and Microsoft Graph.
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
- POST /communications/drafts/{message_id}/approve (administrator; approval audit only)
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

Outbound sending remains disabled. Approving a draft records approval but does not dispatch it. A separate provider send adapter, transactional outbox, Meta 24-hour customer-service-window/template policy, delivery callbacks and audited send worker are still required. Voice is not implemented.

## Database migration
The communications models and Alembic migration `0009_communications` are part of this PR branch. Apply and validate the migration against a disposable PostgreSQL database before deploying the API. No new database table was added for the WhatsApp webhook increment; it reuses the existing communications tables and webhook idempotency ledger.
