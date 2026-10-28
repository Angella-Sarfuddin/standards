# Backend guide (plain language)

This guide explains what the Standards Intelligence backend does and where to look when you need to change it. The backend is the part of the application that reads uploaded files, searches the standards catalogue, and creates downloadable files.

## What happens when someone uses the app?

For a file search, the work happens in a few steps:

1. **The frontend sends a file** to the backend.
2. **The backend reads the file** and pulls out standard numbers, organization names (SDOs), and source row details. It supports Excel, CSV, PDF, Word, and text files.
3. **The user reviews the extracted rows.** At this point, the standards have not been searched yet.
4. **The frontend asks the backend to search.** The backend checks the catalogue, resolves the standards organization, and gathers details such as title, status, edition, price, and classification when available.
5. **The backend returns one result for each request row.** Results can be matched, not found, or have an organization that could not be identified.
6. **The user can request an export.** The backend builds Excel files or ZIP bundles from the results.

The small single-standard search uses the same search engine as the document search. The `/excel/upload` endpoint only extracts rows; it does not also search them.

## The main backend folders

| Folder or file | In everyday terms |
|---|---|
| `backend/app/main.py` | Starts the FastAPI application, connects its route groups, and handles database connection errors. |
| `backend/app/api/` | Defines the web addresses the frontend can call and hands each request to the service that does the work. |
| `backend/app/services/` | Contains the main application work: reading files, searching standards, grouping results, and making exports. |
| `backend/app/services/document_search/` | Smaller helpers used by the document search engine to prepare requests, find matches, apply selection rules, and assemble results. |
| `backend/app/repositories/` | Reads catalogue information from the database. |
| `backend/app/models/` | Describes the database tables the backend expects to use. |
| `backend/app/schemas/` | Pydantic models for JSON request bodies. |
| `backend/app/database/` | Loads `DATABASE_URL` and provides the SQLAlchemy session used by each request. |
| `backend/app/core/` | Shared helpers for standard numbers, identity parsing, formatting, retries, and legacy file conversion. |

### How a request travels through the code

Think of a request as passing through a short chain:

```text
Frontend → API route → Service → Repository → Database
                                ↓
                        Result or export
```

- An **API route** receives the web request.
- A **service** performs the actual task.
- A **repository** gets the needed catalogue information from the database.
- The result travels back to the frontend as JSON, or as a downloadable file.

For example, `POST /documents/search` is declared in `api/document_routes.py`. It runs `DocumentSearchService`. The search service uses the repositories and helper modules to find and enrich results.

## Main web addresses

The backend routes do not start with `/api`. In local development, Vite removes `/api` before forwarding a request to the backend.

| Method and address | What it does |
|---|---|
| `GET /` | Redirects to the interactive API page at `/docs`. |
| `POST /documents/extract` | Reads an uploaded supported document and returns the standards it found. The route limits uploads to 10 MB. |
| `POST /documents/search` | Searches rows that have already been extracted or entered. |
| `POST /standards/search` | Searches a list of standard numbers directly. |
| `POST /excel/upload` | Reads an Excel file and returns extracted rows; it does not search them. |
| `POST /export/excel` | Downloads a quotation workbook. |
| `POST /export/latest-years` | Downloads a workbook of matching standards with current-year information. |
| `POST /export/not-found` | Downloads a workbook of not-found rows. |
| `POST /export/both` | Downloads a ZIP containing quotation and latest-year exports. |
| `POST /export/found-and-not-found` | Downloads a ZIP with quotation and found/not-found files. |

### A small example

To search directly without uploading a file, send this JSON to `POST /standards/search`:

```json
{
  "standards": ["ISO 9001:2015", "ASTM A36"]
}
```

The response contains a `results` list. Each result describes one requested standard and includes whether it matched, its status, and catalogue information when a match was found. The exact returned fields depend on the match and available catalogue data.

To search extracted rows, send them to `POST /documents/search`:

```json
{
  "filename": "customer-list.xlsx",
  "rows": [
    { "sdo_name": "ISO", "displaystdno": "ISO 9001:2015" }
  ]
}
```

That response includes counts, grouped results, and the detailed `results` list. Use `/docs` in a running local backend to try requests interactively and see the live request fields.

## Database in simple terms

The backend needs a standards catalogue database for searching and enrichment. The `DATABASE_URL` setting tells it how to connect. The URL format depends on the database driver; the checked-in example uses MySQL with PyMySQL.

At startup, `backend/app/database/database.py` reads `DATABASE_URL`, creates a shared SQLAlchemy connection pool, and provides a short-lived database session to each request. The same configured database session is used for catalogue matching and result enrichment. The backend returns HTTP `503` when the database is unavailable.

The database models describe tables such as standards, master catalogue entries, publisher/organization records (SDOs), statuses, prices, currencies, and classifications. They show what the code expects; they do not guarantee that a live database has exactly the same columns or data.

## Run the backend locally

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
```

Set `DATABASE_URL` in the repository root `.env` file. Keep real passwords and connection details out of Git.

Then start the API from the `backend` folder, so Python can import the `app` package:

```powershell
Set-Location backend
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` to browse and try the API. These setup steps assume the database can be reached from your machine.

## Files the backend can read

The document extractor recognizes `.xlsx`, `.xls`, `.csv`, `.pdf`, `.docx`, `.doc`, and `.txt` files. Older `.doc` and `.xls` files may need LibreOffice installed for conversion. `/documents/extract` rejects files larger than 10 MB; `/excel/upload` does not currently set the same explicit route-level size limit.

## If something goes wrong

- **The API will not start:** check that `DATABASE_URL` is set. It is read when the database module loads.
- **A search returns 503:** the database may be unavailable or your network/VPN may not reach it.
- **An upload is rejected:** check the extension and, for `/documents/extract`, the 10 MB size limit.
- **No standards were extracted:** inspect the uploaded sheet/text layout and try `/docs` to confirm the endpoint received the expected file.
- **The frontend cannot reach the API after deployment:** production needs a reverse proxy or a frontend API URL that matches the backend routes. The development-only Vite proxy does not ship in the production build.

## Where to read next

- [API reference](API_REFERENCE.md) lists request and response behavior for every route.
- [Database reference](DATABASE_REFERENCE.md) lists the SQLAlchemy models and database setup details.
- [Technical handover](TECHNICAL_HANDOVER.md) describes search internals, modules, and operational behavior in more detail.
- [Known limitations](KNOWN_LIMITATIONS.md) records caveats and unresolved behavior.
- [Repository README](../README.md) has the full local setup instructions.
