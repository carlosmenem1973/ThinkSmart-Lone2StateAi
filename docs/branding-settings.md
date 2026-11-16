# Workspace branding settings

Default identity: **ThinkSmart AI | Loft2 Real Estate**.

An administrator can change the identity in the dashboard under **Identidade visual**. The following values are persisted in PostgreSQL (`brand_settings`) and take effect immediately:

- Product name (default `ThinkSmart AI`)
- Customer name (default `Loft2 Real Estate`)
- Tagline
- Logo URL (HTTPS or a same-origin path such as `/assets/loft2-logo.svg`)
- Primary and accent colours (six-digit hex values)

API:

- `GET /api/v1/settings/branding`: public display metadata only, used by the sign-in screen.
- `PUT /api/v1/settings/branding`: administrator-only update.

The frontend document title is updated to `<product name> | <customer name>`. No frontend rebuild or ECS deployment is needed for normal branding changes. Database migration `0002_brand_settings` creates and seeds the settings record.

This release uses one workspace branding record because the current deployment is for one customer. For a future multi-customer SaaS version, use tenant-scoped branding and enforce tenant isolation in every business-data query; do not simply reuse the singleton settings table.
