# Technical handover

This document describes the repository as its source currently establishes it. Deployment configuration, live database state, and external publisher evidence are outside this code inspection; see [Known limitations](KNOWN_LIMITATIONS.md).

## System overview

The repository has a FastAPI backend under `backend/app/` and a React/Vite frontend under `frontend/`. The backend accepts structured search requests and document uploads, searches local and master catalogue records, enriches matches, and formats spreadsheet or ZIP exports.

The application object is `app` in [`backend/app/main.py`](../backend/app/main.py). The root [`app/__init__.py`](../app/__init__.py) is a compatibility package that points imports at `backend/app`; root [`main.py`](../main.py) re-exports the application. The README's root command is therefore `python -m uvicorn app.main:app --reload`.

## Architecture and request flow

Routes in `backend/app/routes/` declare HTTP inputs and delegate to controllers or export services. Controllers in `backend/app/controllers/` adapt requests to service calls. Repositories encapsulate SQLAlchemy queries. ORM classes are in `backend/app/models/`; there is no separate schemas package in the current tree. Pydantic request models are declared in the relevant route modules.

For a document search, `DocumentController.search_document()` calls `DocumentSearchService.search()` in [`backend/app/services/document_search_service.py`](../backend/app/services/document_search_service.py). The service resolves SDO names, calls `input_preparation.prepare_input_rows()`, then performs display-number and exact/normalized repository lookups. It builds indexes, delegates local matching to `local_matching.match_local_standards()`, sends unresolved rows to `find_master_matches()` / `master_fallback.find_master_matches()`, and passes both result sets to `result_assembly.assemble_results()`. Result helpers perform not-found classification, result de-duplication, and master formatting. Search and fallback stages emit timing output.

`DocumentSearchService.__init__()` constructs `StandardsRepository` and `EnrichmentRepository` with the same SQLAlchemy session. Search, master fallback, price enrichment, and classification enrichment therefore share the configured application database session according to the current code.

### Extracted document-search modules

| Module | Current responsibility |
|---|---|
| `candidate_filtering.py` | Detect revision suffixes, amendments, proposals, UL supplemental publications, and exclusion predicates. |
| `candidate_resolution.py` | Candidate identity/year checks, identifier prefix normalization, API candidate filtering, and current candidate resolution. |
| `candidate_selection.py` | Local, master, and series candidate-selection policies. |
| `enrichment_builder.py` | Build enrichment and price/classification maps from repository results. |
| `family_paths.py` | Identify candidates belonging to an unqualified family root and construct/match part paths. |
| `family_revisions.py` | Determine base edition years and select family revisions. |
| `identity_discovery.py` | Produce SDO aliases and discover/index identity-hint candidates. |
| `input_preparation.py` | Normalize incoming request rows and prepare identity, keys, and source-row metadata. |
| `lifecycle_status.py` | Interpret lifecycle labels embedded in status names and catalogue identifiers. |
| `local_matching.py` | Orchestrate local candidate matching and unresolved-row collection. |
| `lookup_indexes.py` | Build exact, normalized, and standard-number lookup indexes. |
| `master_fallback.py` | Orchestrate master-catalogue lookups and fallback matching. |
| `repository_lookup.py` | Perform grouped display, exact, normalized, and standard-number candidate queries and lookup grouping. |
| `result_assembly.py` | Build ordered results, gather enrichment, and check database-document availability. |
| `result_helpers.py` | Result de-duplication, not-found reason classification, and master-result formatting. |
| `selection_context.py` | Provide a per-call candidate-status map using `ContextVar`. |

The service retains compatibility methods that delegate to helpers. Those wrappers are intentional extension and monkeypatch points; do not bypass them without checking their callers and tests.

## Responsibilities still in the service

`document_search_service.py` still owns the top-level search orchestration and SDO resolution. It also retains compatibility wrappers and several business rules, including publisher-specific replacement and edition behavior, TEMA edition selection, lifecycle visibility and duplicate suppression, requested-edition status recording, enrichment helper callbacks, and API classification filtering. The extracted helper modules do not mean all search policy has become generic or data-driven.

The offline `services/offline/standard_relationship_engine.py` is a separate service component. The current search and export flow does not establish its integration into live candidate selection or result assembly.

## Controllers, services, repositories, models, and utilities

- `StandardsController` maps a list of standard strings to search rows and invokes `DocumentSearchService`.
- `DocumentController` calls `DocumentService` for extraction and `DocumentSearchService` for search, then computes result counts and grouping.
- `ExcelController` extracts an Excel upload and returns rows; its route comment states that search is separate.
- `ExportService` creates XLSX workbooks and ZIP bundles. `GroupingService` groups result objects for the UI/export response.
- `DocumentService` selects an extractor by file extension, expands canonical rows, and attaches source identity.
- `StandardsRepository` queries the search table and SDO catalogue. `EnrichmentRepository` queries master standards, status, price, currency, and classification records.
- Utilities include identity parsing/normalization, expression parsing, display formatting, retry handling, legacy Office conversion, and API classification filtering.

The API routes and body/response behavior are listed in [API reference](API_REFERENCE.md). ORM fields and database configuration are listed in [Database reference](DATABASE_REFERENCE.md).

## File processing and exports

`DocumentService.SUPPORTED_EXTENSIONS` maps `.xlsx` and `.xls` to Excel, `.pdf` to PDF, `.docx` and `.doc` to Word, `.txt` to text, and `.csv` to CSV processing. Legacy `.doc` and `.xls` conversion uses LibreOffice through `utils/legacy_office.py`; `LIBREOFFICE_PATH` and `STANDARDS_TEMP_DIR` are optional environment controls. The `/documents/extract` route enforces a 10 MB limit; the `/excel/upload` route has no corresponding explicit size check in its route function.

Export routes call `ExportService`. Several routes also rerun search for specific API RP 1176 or NACE MR0103 requests; the combined found/not-found export additionally expands series rows. This behavior is confirmed in `backend/app/routes/export_routes.py`; its intended product contract and effect on user-submitted results require owner confirmation.

## Operations

The runtime requires `DATABASE_URL` at import time because `backend/app/db/database.py` creates the SQLAlchemy engine during module initialization. Actual connection/query activity occurs when database operations run; this handover did not connect. The example URL uses MySQL/PyMySQL, but the deployed engine and connection/network requirements are not verified.

The app maps SQLAlchemy `OperationalError` to HTTP 503 in `main.py`. CORS is configured for HTTP/HTTPS origins on `localhost` and `127.0.0.1`; this is the code's current configuration, not a deployment security recommendation. No authentication dependency is declared in the inspected route functions. Production authentication, proxy, TLS, process count, and CORS policy are not established by this repository inspection.

Setup, environment configuration, startup, and test commands are in the root [README](../README.md). Database settings and model details are in [Database reference](DATABASE_REFERENCE.md).

## Tests

The suite is under `backend/tests/` and uses `unittest`. The documented root command is:

```powershell
python -m unittest discover -s backend/tests -v
```

There are focused test files for identity parsing, candidate filtering/resolution/selection, family behavior, input preparation, local and master matching, lifecycle status, result assembly, enrichment, repository lookup, deduplication, relationship-engine behavior, extraction formats, exports, and database dependency cleanup. The previously reported 251 passing tests are historical; no suite was run for this handover documentation task.
