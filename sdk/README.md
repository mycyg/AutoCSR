# AutoCSR SDKs

This directory holds language-specific client SDKs generated from the
live `openapi.json` document.

## Generation

1. Start the backend on port 8766:

   ```bash
   cd backend
   .venv/Scripts/uvicorn app.server.main:app --port 8766
   ```

2. In another terminal, run the generator:

   ```bash
   python scripts/generate_sdk.py            # both languages
   python scripts/generate_sdk.py --ts       # TypeScript only
   python scripts/generate_sdk.py --py       # Python only
   python scripts/generate_sdk.py --url http://other-host/openapi.json
   ```

   The TypeScript output uses
   [`openapi-typescript-codegen`](https://github.com/ferdikoomen/openapi-typescript-codegen)
   (axios client). The Python output uses
   [`openapi-python-client`](https://github.com/openapi-generators/openapi-python-client).

   Both generators are optional — if neither tool is installed the
   script logs a `[skip]` line and exits cleanly.

## Output layout

```
sdk/
  ts/        <- TypeScript SDK
  py/        <- Python SDK (one package per OpenAPI title)
  example.ts <- Hello-world snippet for the TS client
  example.py <- Hello-world snippet for the Python client
```

## TypeScript example

```ts
import { OpenAPI, ProjectsService } from "./ts";

OpenAPI.BASE = "http://127.0.0.1:8766";

const projects = await ProjectsService.listProjectsApiProjectsGet();
console.log(projects);
```

## Python example

```python
from autocsr_api_client import Client
from autocsr_api_client.api.projects import list_projects_api_projects_get

client = Client(base_url="http://127.0.0.1:8766")
projects = list_projects_api_projects_get.sync(client=client)
print(projects)
```

(The exact module / function names depend on the generator version.)

## Notes

* SDK output is gitignored by default. Re-run the script after any
  route or schema change.
* The OpenAPI document is the contract: keep
  `app/server/main.py` `openapi_tags` and per-route `tags=[]` arguments
  up to date so generated SDKs stay organised.
