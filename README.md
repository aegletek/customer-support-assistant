# Augent Use Case Template

Use this private GitHub template to create an independently owned application
powered by the shared `augent-core` package. It starts with a deterministic,
two-agent native workflow so a team can validate its application boundary
before adding LLMs, databases, observability, or other external services.

## Create a use case

1. In GitHub, select **Use this template**, create a private repository, and
   clone it.
2. Initialize the project once:

   ```powershell
   python scripts/initialize.py `
     --project-name customer-risk-assistant `
     --package-name customer_risk_assistant `
     --display-name "Customer Risk Assistant"
   ```

3. Copy `.env.example` to `.env`. Never commit `.env` or credentials.
4. Install Augent Core using one approved source, then install this application.

## Install with private GitHub source

For local development, install the pinned core release and then this repo:

```powershell
python -m pip install `
  "augent-core @ git+https://github.com/nagaraju-ssa/augent-repo.git@v0.1.0"
python -m pip install -e ".[test]"
```

Git authentication must come from the developer's credential manager or an
approved environment variable. Do not place a token in `pyproject.toml`, a
requirements file, or a committed URL.

## Install with Azure Artifacts

Authenticate with the team's approved Azure Artifacts credential provider,
then supply the feed as an extra index:

```powershell
$env:PIP_EXTRA_INDEX_URL = "https://pkgs.dev.azure.com/ORG/PROJECT/_packaging/FEED/pypi/simple/"
python -m pip install -e ".[test]"
```

The declared `augent-core==0.1.0` dependency is then resolved from the private
feed. Replace the placeholder feed URL with the organization-approved value.

## Run the starter

```powershell
python -m pytest
python -m augent_usecase.cli --task "Review customer C-100"
uvicorn augent_usecase.api:create_app --factory --reload
```

The API exposes `GET /health` and `POST /execute`:

```json
{"task": "Review customer C-100"}
```

After initialization, use the renamed package in the CLI and Uvicorn commands.

## CI configuration

The workflow defaults to the private GitHub source. Add this repository secret:

- `AUGENT_CORE_GITHUB_TOKEN`: read-only fine-grained token for the private
  `nagaraju-ssa/augent-repo` repository.

Optional repository variables and secrets:

- `AUGENT_CORE_REF`: approved immutable core tag or commit; the workflow
  defaults to `v0.1.0`.
- `AUGENT_CORE_SOURCE=azure`: resolve the core package from Azure Artifacts.
- `AUGENT_PYPI_INDEX_URL`: authenticated Azure Artifacts Python index URL.

## What teams replace

- `tools.py`: injected clients for approved external systems;
- `agents.py`: one focused capability per agent;
- `workflow.yaml`: orchestration and execution adapter;
- `config.py` and `.env.example`: typed non-secret configuration names;
- tests: deterministic unit, workflow, API, and integration coverage.

Keep business models and calculations outside agents where possible. Add live
systems one boundary at a time, and preserve the public Augent Core contracts.

The complete training path, checklist, architecture guidance, security rules,
and production-readiness criteria are maintained in the Augent Core repository
under `docs/usecase-development/`.
