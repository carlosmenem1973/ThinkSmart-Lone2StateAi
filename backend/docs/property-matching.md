# CRM property matching

## Scope

The matching service reuses the existing `contacts` and `leads` tables. It does not create a duplicate property catalogue or infer legal ownership. Results are calculated on demand from current database records, so updates to a contact or lead are reflected on the next request.

## Endpoints

- `GET /api/v1/matching/contacts/{contact_id}/properties`: clients receive ranked property leads; owners receive leads associated by exact email/phone.
- `GET /api/v1/matching/leads/{lead_id}/contacts?contact_type=client`: rank matching client contacts for a property.
- `GET /api/v1/matching/leads/{lead_id}/contacts?contact_type=owner`: associate the owner contact by exact email/phone.

Both sides enforce the current seller assignment scope. Admin/manager roles can search the workspace. Results are limited and do not expose contact email/phone in buyer matches.

## Scoring

The deterministic 0-100 score uses available, explicitly stored criteria: municipality/district, price vs. budget, property type, bedrooms, requested area, and operation (buy/rent). Unknown values are reported as missing and are not fabricated. Only fields with a stated client criterion contribute to the denominator. A score is a ranking aid, not a guarantee of suitability.

Owner linking uses exact email or digit-normalised phone. It only links CRM records; `owner_identity_verified` remains false because a matching contact record does not prove legal ownership.

## Communications boundary

Matching never sends messages. WhatsApp/Email/SMS agents can call this service to prepare recommendations, but outbound communication remains subject to channel permissions, suppression checks, and the approval/autonomy policy. Discovered web leads are not proof of ownership or permission to contact.
