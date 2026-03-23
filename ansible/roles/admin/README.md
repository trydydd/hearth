# Admin Role — Backend

The admin backend is a lightweight [FastAPI](https://fastapi.tiangolo.com/)
application that provides the JSON API consumed by the admin UI.

## Prerequisites

- Python 3.11+
- A virtual environment (recommended)

## Running Locally

```bash
# 1. From repository root, create and activate the shared dev virtualenv
python3 -m venv .venv
source .venv/bin/activate

# 2. Install backend dependencies into the root virtualenv
pip install -r ansible/roles/admin/files/backend/requirements.txt

# 3. Run the backend from its source directory
cd ansible/roles/admin/files/backend
uvicorn main:app --reload
```

Do not create a local `.venv` inside `ansible/roles/admin/files/backend`; role
payload directories are deployable artifacts and should stay free of local
runtime state.

The server listens on `http://127.0.0.1:8000` by default.

## Verifying the Health Endpoint

```bash
curl http://127.0.0.1:8000/healthz
# {"status":"ok"}
```

## Running the Tests

From the **repository root**:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_backend.py -v
```

## Configuration

The backend reads `cafe.yaml` using the following resolution order:

1. The explicit `path` argument passed to `load_config()`.
2. The `CAFEBOX_CONFIG` environment variable.
3. `cafe.yaml` in the current working directory (i.e. the repo root when you
   run `uvicorn` from there).

Override the default by setting the environment variable:

```bash
CAFEBOX_CONFIG=/path/to/cafe.yaml uvicorn main:app
```

## Interactive API Docs

When running locally, FastAPI automatically serves interactive docs at:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## OpenAPI Contract

A static copy of the OpenAPI schema is committed at
`ansible/roles/admin/files/backend/openapi.json`.
You can browse it without running the service — paste it into
[editor.swagger.io](https://editor.swagger.io) or open it in any OpenAPI-aware
tool (Insomnia, Postman, VS Code REST Client, etc.).

Regenerate after adding or changing routes:

```bash
cd ansible/roles/admin/files/backend
python3 -c "
from main import app
import json
schema = app.openapi()
with open('openapi.json', 'w') as f:
    json.dump(schema, f, indent=2)
    f.write('\n')
"
```
