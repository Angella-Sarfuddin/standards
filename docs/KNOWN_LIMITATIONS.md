# Known limitations and confirmation items

This list separates repository-confirmed facts from deployment, data, and product questions that cannot be resolved by inspecting source alone. No external publisher sources or database were consulted for this handover.

## Runtime and deployment details to confirm

- **Python version:** The root README states Python 3.12+, while `backend/requirements.txt` does not encode a supported version. Confirm the supported runtime with the deployment owner.
- **Database URL discrepancy:** `DATABASE_URL` is required by `backend/app/db/database.py`. `ENRICHMENT_DATABASE_URL` appears in `backend/.env.example` and README configuration text but is not read by the application database module; `backend/scripts/inspect_databases.py` reads it. Confirm whether it is only for that utility or needed in any deployed workflow.
- **Database engine and network:** The example URL is MySQL/PyMySQL. The actual production dialect, server version, VPN/network path, connection pool limits, credentials provider, and failover behavior are not established here.
- **Schema deployment:** Model classes declare some constraints but no SQLAlchemy `ForeignKey` or `relationship()` declarations. Live DDL, additional constraints/indexes, and migration/rollback procedures require database-owner confirmation. See [Database reference](DATABASE_REFERENCE.md).
- **Production server and API routing:** README documents a local Uvicorn command. Worker count, process manager, container setup, reverse proxy, TLS, health checks, and production command are not defined in the inspected application files. The frontend defaults to `/api`, but only the Vite development server proxies that prefix and strips it before forwarding. Production must provide equivalent `/api/*` forwarding with the prefix removed, or build the frontend with `VITE_API_BASE_URL` set to a backend base that serves the registered route paths directly. The deployment owner must supply and verify this routing.
- **Security:** Route declarations inspected here do not attach authentication or authorization dependencies. This does not establish whether a gateway or other external layer protects the deployed service. Confirm access controls, CORS policy, and upload limits with the deployment owner.
- **Frontend runtime:** `frontend/package.json` defines Vite scripts but no Node.js version pin was found. The Vite proxy target is localhost and should not be mistaken for production routing.

## Product and catalogue behavior requiring review

- **Publisher-specific search and lifecycle logic:** `document_search_service.py` retains publisher-specific behavior, including the BIS replacement helper, NACE MR0103 edition handling, HI replacement handling, IEEE metadata lookup, TEMA edition naming/selection, and API candidate filtering. The code proves these branches exist and shows their effects; it does not independently prove the underlying publisher relationships or current catalogue facts.
- **IEEE mappings:** `backend/app/services/ieee_official_metadata.py` contains metadata used by result assembly. The presence of a source URL in code is not proof that the exact source edition has the claimed relationship to the target. Publisher evidence and edition scope need review.
- **BIS and HI replacement claims:** `_bis_replacement_standard()` and `_official_hi_replacement()` can affect replacement output. Their factual scope should be checked against authoritative, edition-specific evidence and approved catalogue data before being described as publisher-verified.
- **NACE / ISO 17945 identity:** `_official_nace_mr0103_edition()` and related export refresh logic can direct requests toward a canonical catalogue record. Confirm the intended identity/adoption contract and the data owner's canonical record policy.
- **TEMA selection:** The service recognizes TEMA edition-style requests, applies historical-year logic, and selects the latest visible numbered edition. Confirm the product contract for yearless requests and the 2026 naming transition with the product and data owners.
- **Export refresh:** `backend/app/routes/export_routes.py` reruns search for API RP 1176 and selected NACE MR0103 requests in several export endpoints; the found/not-found bundle also expands series requests. Refreshed rows may differ from the submitted result payload. Confirm that this refresh behavior is intended and that export output should not always use the user's last search result.
- **Pricing and classification:** `enrichment_builder.py` and `EnrichmentRepository` contain format/alias resolution and classification hierarchy handling. These are implementation rules; source inspection alone cannot confirm every publisher's current pricing or classification policy.
- **Relationship engine integration:** `backend/app/services/offline/standard_relationship_engine.py` is a standalone offline component in the current tree. The search and export pipeline does not establish a persistent relationship store or live resolver integration.

## Verification status and test evidence

The repository contains focused tests for search identity, candidate filtering/selection, family handling, lifecycle status, result assembly, enrichment, export behavior, file extraction, database dependency cleanup, and the offline relationship engine. A prior report recorded 251 passing tests, but that is historical and was not rerun for this documentation task. Consult the test command in the root [README](../README.md) for a fresh result.

Tests using mocks and fixtures do not prove production database connectivity, live catalogue correctness, publisher claims, export behavior in a deployed browser, or external authentication. Those require separate approved validation.

## Owner decisions before making claims in customer-facing documentation

1. Confirm the production Python and Node versions, backend launch command, and deployment topology.
2. Confirm whether `ENRICHMENT_DATABASE_URL` belongs only to the inspection utility.
3. Confirm database dialect, schema/constraint source of truth, migration process, and connection/network requirements.
4. Approve the API's intended authentication, authorization, CORS, and upload-size policies.
5. Confirm the export refresh contract and the publisher-specific edition/replacement behaviors listed above.
6. Identify who approves canonical catalogue identity and relationship corrections, and what evidence qualifies as verified.
