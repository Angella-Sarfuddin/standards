# API reference

This reference reflects route declarations and response construction in `backend/app/api/`. The application does not declare explicit `response_model` values for these routes. Export bodies are typed as generic lists/dictionaries in route signatures, so this document does not invent stricter schemas.

The FastAPI app registers routers in [`backend/app/main.py`](../backend/app/main.py). Backend routes below do **not** include `/api`; the frontend's Vite development proxy removes that prefix before forwarding.

## General

| Method and path | Request | Response behavior | Source |
|---|---|---|---|
| `GET /` | No body | Redirect response to `/docs`; excluded from OpenAPI schema. | `root()` in [`backend/app/main.py`](../backend/app/main.py) |

Database-backed routes depend on `get_db()` unless noted. `DATABASE_URL` configuration is documented in [Database reference](DATABASE_REFERENCE.md).

## Search and upload

| Method and path | Request | Response behavior | Source |
|---|---|---|---|
| `POST /standards/search` | JSON `StandardsSearchRequest`: `standards: list[str]` | JSON object with `results`; `search_standards()` turns each non-empty string into a search row. A one-item list can be used for one designation; there is no separate single-standard route. | `StandardsSearchRequest` in [`standards.py`](../backend/app/schemas/standards.py); `search_standards()` in [`standards_routes.py`](../backend/app/api/standards_routes.py) |
| `POST /documents/search` | JSON `DocumentSearchRequest`: `rows: list[dict]`; optional `filename: str | None` | JSON object containing `filename`, `total`, `input_requests`, `duplicates_collapsed`, `matched`, `not_found`, `sdo_not_found`, `grouping`, and `results`. | `DocumentSearchRequest` in [`document.py`](../backend/app/schemas/document.py); `search_document()` in [`document_routes.py`](../backend/app/api/document_routes.py) |
| `POST /documents/extract` | Multipart form upload: required `file` | JSON object with `filename`, `total`, and extracted `results`. The route rejects a missing filename (400), files over 10 MiB (413), and unsupported extensions (400). | `extract_document()` in [`document_routes.py`](../backend/app/api/document_routes.py) |
| `POST /excel/upload` | Multipart form upload: required `file` | JSON object with `filename`, `total`, and extracted `results`. This endpoint extracts rows; it does not invoke standards search in its controller. | `upload_excel()` in [`excel_routes.py`](../backend/app/api/excel_routes.py) |

`DocumentService` currently recognizes `.xlsx`, `.xls`, `.pdf`, `.docx`, `.doc`, `.txt`, and `.csv`. This extension list is implementation behavior, not a guarantee that every malformed or oversized file is accepted. `/excel/upload` has no explicit size check in its route function.

## Export

All exports return a file response with `Content-Disposition`. Export responses are binary, not JSON. Filenames and media types below are taken from `backend/app/api/export_routes.py`.

| Method and path | Request | Response |
|---|---|---|
| `POST /export/excel` | JSON list of result dictionaries | XLSX attachment `standards_quotation.xlsx`; route refreshes selected catalogue requests before grouping/export. |
| `POST /export/latest-years` | JSON list of result dictionaries | XLSX attachment `standards_latest_years.xlsx`; route refreshes selected catalogue requests. |
| `POST /export/both` | JSON object with optional `quotation_results` and `latest_year_results` lists | ZIP attachment `standards_exports.zip`; both lists pass through selected catalogue refresh logic. |
| `POST /export/not-found` | JSON list of result dictionaries | XLSX attachment `not_found_standards.xlsx`; this route does not take a database dependency or call the refresh helper. |
| `POST /export/found-and-not-found` | JSON object with optional `quotation_results` and `all_results` lists | ZIP attachment `standards_found_and_not_found.zip`; selected catalogue refresh and series expansion are applied. |

`_refresh_official_catalog_rows()` currently dispatches API RP 1176 and NACE MR0103-specific refresh behavior. `_expand_series_export_rows()` is used by `/export/found-and-not-found`. These implementation details and unresolved product questions are discussed in [Known limitations](KNOWN_LIMITATIONS.md).

## Errors and operational behavior

- `main.handle_database_operational_error()` maps SQLAlchemy `OperationalError` to HTTP 503 with a generic database-unavailable message.
- `/documents/search` also catches `OperationalError` and returns 503. Other exceptions in that route are returned as HTTP 500 with a generic message.
- `/documents/extract` returns 400 for supported input validation errors and 500 for other extraction exceptions.
- No explicit authentication dependency or authorization scheme appears on the inspected route declarations. This observation does not establish deployment-level access controls.

## Frontend path mapping

The frontend defaults its API base to `/api` in `frontend/src/api/index.js`; `frontend/vite.config.js` proxies `/api` to `http://127.0.0.1:8000` and strips the prefix during development. Vite's `server.proxy` is not included in production builds. A production reverse proxy must route `/api/*` to the backend and strip `/api` while preserving the registered route path, or the frontend must be built with `VITE_API_BASE_URL` set to a backend base that serves these route paths directly. `/api` is not registered as a FastAPI prefix. See the root [README](../README.md#production-api-routing) and [Known limitations](KNOWN_LIMITATIONS.md) for the deployment requirement.
