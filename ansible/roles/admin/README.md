# Admin Role — Backend

The admin backend is a lightweight [FastAPI](https://fastapi.tiangolo.com/)
application that provides the JSON API consumed by the admin UI.

## Prerequisites

- Python 3.11+
- A virtual environment (recommended)

## Running Locally

```bash
# 1. Navigate to the backend directory
cd ansible/roles/admin/files/backend

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the development server
uvicorn main:app --reload
```

The server listens on `http://127.0.0.1:8000` by default.

## Verifying the Health Endpoint

```bash
curl http://127.0.0.1:8000/healthz
# {"status":"ok"}
```

## Running the Tests

From the **repository root**:

```bash
python -m pytest tests/test_admin_backend.py -v
```

## Configuration

The backend reads `cafe.yaml` from the repository root.  When running the
server locally the default path resolution (`config.py`) walks five directories
up from the backend folder to find `cafe.yaml`.  You can override this by
setting the `CAFEBOX_CONFIG` environment variable to an explicit path:

```bash
CAFEBOX_CONFIG=/path/to/cafe.yaml uvicorn main:app
```

## Interactive API Docs

When running locally, FastAPI automatically serves interactive docs at:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
