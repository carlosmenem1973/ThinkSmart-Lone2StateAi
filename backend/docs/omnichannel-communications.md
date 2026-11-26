# ThinkSmart AI — Omnichannel Communications

## Product decisions
- One central business account owns WhatsApp, SMS and Microsoft 365 email channels.
- Hybrid autonomy: low-risk service replies can become automated after provider and policy validation; commercial outreach and sensitive actions require human approval.
- Voice is out of scope for this increment.
- Customers and property owners are represented by CRM contacts, with contact_type set to client or owner.

## Implemented API foundation
- Central channel registry for Meta WhatsApp Cloud API, AWS End User Messaging and Microsoft Graph.
- Per-contact, per-channel, per-purpose consent records with evidence and revocation timestamps.
- Unified communication threads linked to CRM contacts and optional leads.
- Message history model with provider IDs and delivery states.
- Webhook event idempotency ledger.
- Authenticated inbox, consent management, outbound draft creation and administrator approval audit.
- do_not_contact is a hard stop; marketing drafts require unexpired channel-specific consent.

All routes are under /api/v1:
- GET /communications/overview
- POST /communications/channels (administrator)
- PUT and GET /communications/contacts/{contact_id}/consent
- POST /communications/drafts
- GET /communications/inbox
- GET /communications/inbox/{thread_id}/messages
- POST /communications/drafts/{message_id}/approve (administrator)

## Delivery boundary
This increment does not send messages. Channel records are created disabled; approval records approval but does not dispatch. Provider credentials must be stored in AWS Secrets Manager, never in the database configuration JSON or source code.

Before enabling delivery, implement and test:
1. Meta webhook signature verification, template/window policy, status callbacks and deduplication.
2. AWS SMS origination identity/registration, opt-out keyword handling and delivery callbacks.
3. Microsoft Graph OAuth, per-mailbox authorization, encrypted token persistence and sendMail.
4. Transactional outbox/worker with retries, idempotency and dead-letter handling.
5. Tests for access control, consent expiry/revocation, suppression and provider failures.

## Database migration
SQLAlchemy models are registered in the application. The repository currently has no backend Alembic directory. A database migration must be established and applied to RDS before the new endpoints are used. Registering ORM models does not alter an existing database automatically.
