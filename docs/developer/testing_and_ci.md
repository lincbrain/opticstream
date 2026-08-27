---
title: Testing and CI
---

# Testing and CI

Tests are split into unit tests, which do not require external services, and
integration tests backed by a Prefect server and PostgreSQL.

Run the unit tests locally with:

```bash
uv run pytest -m "not integration" -ra
```

Run the integration tests locally after starting the server profile:

```bash
docker compose --profile server up -d
uv run prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api
uv run pytest -m integration -ra
docker compose --profile server down
```

The `Tests` GitHub Actions workflow runs these as separate jobs. The unit job
requires no services. The integration job starts Prefect and PostgreSQL with
Docker Compose on the GitHub-hosted runner, waits for the API health endpoint,
runs the integration-marked tests, and always stops the services afterward.

Both jobs run for pushes and pull requests, and can also be started manually
with the workflow's **Run workflow** button.
