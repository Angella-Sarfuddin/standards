# Standards Intelligence Backend

Standards Intelligence is a full-stack application for extracting standard designations from documents, finding catalog matches, reviewing availability and pricing, and exporting quotation and not-found workbooks.

## Project layout

- `backend/app/` contains the FastAPI application and its routes, controllers, repositories, models, services, extractors, and utilities.
- `backend/app/services/document_search/` contains the extracted document-search helpers.
- `backend/tests/` contains the Python test suite.
- `frontend/` contains the React and Vite application.
- `backend/scripts/inspect_databases.py` is a database inspection utility.

The API reads standards and enrichment records from configured databases. Uploaded Excel, CSV, PDF, Word, and TXT files are processed by the backend extractors; generated Excel exports are returned as in-memory responses. Legacy Office conversion uses the system temporary directory and the ignored repository `.standards-tmp/` fallback.

## Requirements

- Python 3.12 or newer and a supported database server.
- Node.js and npm.
- LibreOffice is optional and is used for legacy `.doc` conversion when available.

## Configure the backend

Create and activate a virtual environment from the repository root, then install the backend dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
```

Set `DATABASE_URL` and `ENRICHMENT_DATABASE_URL` in the root `.env`. The existing local `.env` is kept at the repository root. For a new checkout, copy `backend/.env.example` to `.env` and replace its safe placeholders with local database settings. Do not commit credentials.

Start the API from the repository root:

```powershell
python -m uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; FastAPI's interactive documentation is at `/docs`.

## Configure the frontend

Install and start the Vite application:

```powershell
cd frontend
npm install
npm run dev
```

The frontend defaults to `http://127.0.0.1:8000` for the API. To use another backend URL, copy `frontend/.env.example` to `frontend/.env.local`, set `VITE_API_BASE_URL`, and restart Vite. The backend CORS configuration currently permits the Vite development origins on localhost and 127.0.0.1, port 5173.

Available frontend scripts are `npm run dev`, `npm run build`, `npm run lint`, and `npm run preview`.

## Run tests

From the repository root, with the backend virtual environment active:

```powershell
python -m unittest discover -s backend/tests -v
```

The top-level `requirements.txt`, `main.py`, `database.py`, and `app` package are compatibility entry points for existing repository-root commands and imports. New backend code lives under `backend/app/`.
