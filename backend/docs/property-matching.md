# CRM property matching

## Scope

The matching service reuses the existing `contacts` and `leads` tables. It does not create a duplicate property catalogue or infer legal ownership. Results are calculated on demand from current database records, so updates to a contact or lead are reflected on the next request.

## Endpoints

- `GET /api/v1/matching/contacts/{contact_id}/properties`: clients receive ranked property leads; owners receive leads associated by exact email/phone.
- `GET /api/v1/matching/leads/{lead_id}/contacts?contact_type=client`: rank matching client contacts for a property.
- `GET /api/v1/matching/leads/{lead_id}/contacts?contact_type=owner`: associate the owner contact by exact email/phone.

Both sides enforce the current seller assignment scope. Admin/manager roles can search the workspace. Results are limited and do not expose contact email/phone in buyer matches.

## Agent integration

The authenticated `POST /api/v1/agents/{agent_id}/run` endpoint accepts optional CRM identifiers for `lead-qualifier`, `follow-up-assistant`, and `owner-intelligence`:

```json
{
  "input": "Resume os melhores candidatos e indica os dados em falta.",
  "lead_id": 123
}
```

For a client-to-property search, pass `contact_id` instead of `lead_id`. Exactly one identifier is required when CRM context is requested. The endpoint applies the same seller assignment scope as the matching API and returns a 404 when the record is outside that scope.

The agent context is capped to the top 10 matches and omits phone numbers and email addresses. Buyer matches may include CRM contact IDs and names for the authenticated operator's workflow. Owner matching is based only on exact email or digit-normalised phone and explicitly does not prove legal ownership. Matching context is supplied as data to the model; it is not a command to contact anyone.

Example PowerShell request body:

```powershell
$body = @{
  input = "Resume os clientes mais compatíveis. Não prepares nem envies mensagens."
  lead_id = 123
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "$env:THINKSMART_API_URL/api/v1/agents/follow-up-assistant/run" `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body $body
```

## Scoring

The deterministic 0-100 score uses available, explicitly stored criteria: municipality/district, price vs. budget, property type, bedrooms, requested area, and operation (buy/rent). Unknown values are reported as missing and are not fabricated. Only fields with a stated client criterion contribute to the denominator. A score is a ranking aid, not a guarantee of suitability.

Owner linking uses exact email or digit-normalised phone. It only links CRM records; `owner_identity_verified` remains false because a matching contact record does not prove legal ownership.

## Communications boundary

Matching never sends messages. The agent integration only adds CRM context to Bedrock analysis. It does not invoke WhatsApp, SMS, email, provider adapters, or draft-approval endpoints. Any later outbound contact must still pass channel permissions, suppression checks, consent/purpose rules, and human approval. Discovered web leads are not proof of ownership or permission to contact.

The WhatsApp provider/webhook/worker integration remains separate follow-up work; no WhatsApp channel is activated by this change.
