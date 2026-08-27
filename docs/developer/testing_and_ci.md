---
title: Testing and CI
---

# Testing and CI

Tests are split into unit tests, which do not require external services, and
integration tests backed by a Prefect server and PostgreSQL.

Run the unit tests locally with:

```bash
uv run pytest -ra
```

Pytest excludes tests marked `integration` by default, so the local command
does not connect to Prefect or Docker.

The `Tests` GitHub Actions workflow runs unit and integration tests as separate
jobs. The unit job requires no services. The integration job overrides the
local default, starts Prefect and PostgreSQL with Docker Compose on the
GitHub-hosted runner, waits for the API health endpoint, runs the
integration-marked tests, and always stops the services afterward.

Both jobs run for pushes and pull requests, and can also be started manually
with the workflow's **Run workflow** button.
