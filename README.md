# Standards Intelligence

Standards Intelligence extracts standard designations from documents, searches the standards catalogue, presents match and availability information, and generates Excel/ZIP exports. The repository contains a FastAPI backend in `backend/` and a React/Vite frontend in `frontend/`.

For detailed source-backed documentation, see [Technical handover](docs/TECHNICAL_HANDOVER.md), [API reference](docs/API_REFERENCE.md), [Database reference](docs/DATABASE_REFERENCE.md), and [Known limitations](docs/KNOWN_LIMITATIONS.md).

## Prerequisites

- Python **3.12 or newer** is the version stated by the project README. The pinned requirements do not independently declare a Python version constraint.
- Node.js and npm for the frontend. The repository does not pin their versions.
- Access to the configured standards database for database-backed API operations. The repository's example connection URL uses MySQL with PyMySQL; the deployed engine and network requirements must be confirmed with the deployment owner.
- LibreOffice is optional. It is used for legacy `.doc` and `.xls` conversion when installed; ordinary `.docx` and `.xlsx` processing does not require it.

## Install backend dependencies

Run these PowerShell commands from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
```

The root `requirements.txt` is a compatibility include of `backend/requirements.txt`.

## Configure the backend

The application requires `DATABASE_URL`. The database module loads `.env` from the repository root when present; otherwise it checks `backend/.env`. If neither exists, the process environment must provide `DATABASE_URL`. The application creates one SQLAlchemy engine and uses the request's database session for search and enrichment.

For a new checkout, create a local file from the safe example only if a root `.env` does not already exist:

```powershell
if (-not (Test-Path .env)) { Copy-Item backend/.env.example .env }
```

Edit the local file or set `DATABASE_URL` in the process environment. Never commit credentials. The example also contains `ENRICHMENT_DATABASE_URL`; application startup does not require or read it. The database inspection utility under `backend/scripts/` does read it.

Optional settings:

- `LIBREOFFICE_PATH` points to a LibreOffice executable if it is not discoverable on `PATH`.
- `STANDARDS_TEMP_DIR` selects a preferred temporary directory for legacy Office conversion.

See [Database reference](docs/DATABASE_REFERENCE.md) for model and configuration details.

## Start the backend

From the repository root, with the virtual environment active and `DATABASE_URL` configured:

```powershell
python -m uvicorn app.main:app --reload
```

The compatibility package at the repository root resolves `app` to `backend/app`. The application normally listens at `http://127.0.0.1:8000`; `/` redirects to `/docs`. The repository does not define production worker, process-manager, or deployment settings.

## Start the frontend

In a separate PowerShell window:

```powershell
Set-Location frontend
npm install
npm run dev
```

During Vite development, frontend requests use `/api`; the Vite proxy forwards them to `http://127.0.0.1:8000` and removes the `/api` prefix. `/api` is not a FastAPI route prefix. To use a different API host, create `frontend/.env.local`, set `VITE_API_BASE_URL`, and restart Vite. The checked-in frontend example contains only a commented placeholder.

### Production API routing

The Vite `server.proxy` setting applies only to the development server; it does not proxy requests from a production build. With the default `VITE_API_BASE_URL=/api`, the browser requests paths such as `/api/documents/search`, while FastAPI registers `/documents/search` without the `/api` prefix. A production web server or reverse proxy must therefore forward `/api/*` to the backend and strip the leading `/api` while preserving the remaining route path. Alternatively, set `VITE_API_BASE_URL` before `npm run build` to the backend API base that serves the registered paths directly. Vite embeds this setting in the build. No production proxy or deployment configuration is present in this repository; the deployment owner must configure and verify this routing.

Other frontend scripts, defined in `frontend/package.json`, are `npm run build`, `npm run lint`, and `npm run preview`.

## Run backend tests

From the repository root, with the backend virtual environment active:

```powershell
python -m unittest discover -s backend/tests -v
```

The suite uses `unittest`; see [Technical handover](docs/TECHNICAL_HANDOVER.md#tests) for the test areas. No test result is asserted by this documentation.
