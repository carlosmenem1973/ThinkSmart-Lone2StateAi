# Property discovery: next implementation stages

The current feature searches public web sources through AgentCore Web Search, asks Nova Lite to synthesise the retrieved evidence, and stores the report and source URLs in the existing audit log.

It does **not** currently establish that a named person owns a property, create verified leads, or contact owners. A search result is not proof of ownership or permission to contact.

## Staged roadmap

1. **Discovery report (current)** — recurring/manual search, source URLs, report, human review.
2. **Candidate extraction** — normalise candidate property records from source-backed results; preserve the original URL and retrieval date; mark every extracted field with its source and confidence.
3. **Deduplication** — compare candidates against existing leads and previous candidates using normalised address, municipality, portal reference and canonical URL. Do not merge records automatically when identity is ambiguous.
4. **Human qualification queue** — let an authorised user accept, reject, or request more research. Only accepted candidates become CRM leads.
5. **Owner identity and contact eligibility** — keep owner identity unverified until supported by reliable evidence. Record lawful basis, channel permission/consent where required, source, purpose and retention metadata before any outreach draft is made available.
6. **Approved outreach** — generate a draft only. A human must approve the exact recipient, channel and message. No automatic calls, email, SMS or WhatsApp.

## Data integrity constraints

- Reuse existing CRM entities and migrations only after reviewing their schema and access-control rules.
- Never overwrite a lead's verified fields with lower-confidence web data.
- Preserve seller/tenant visibility rules; global search results must not leak across tenants or seller scopes.
- Store source URLs and evidence separately from asserted owner identity.
- Provide deletion/retention handling and audit events for review decisions.
- Treat page content and search snippets as untrusted input to the model.

## Acceptance criteria before automatic lead creation

- Deterministic deduplication tests, including address variations and missing addresses.
- Tests proving seller/tenant scoping and no cross-tenant disclosure.
- Every candidate field can be traced to a source URL.
- No owner is labelled verified based only on a search snippet.
- Human acceptance is required before inserting a lead.
- No external contact can be sent from discovery or qualification tasks.
