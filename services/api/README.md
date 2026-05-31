# shinkai-api

FastAPI backend for shinkai's long-running investment research agent.

```bash
uv sync
uv run uvicorn shinkai_api.main:app --reload --port 8000
```

V0 responsibilities:

- run lifecycle and event stream
- shinkai harness primitives
- research graph persistence interface
- checkpoint review interface
- eval and A2A message contracts
