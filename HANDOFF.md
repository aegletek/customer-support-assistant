# Customer Support Assistant handoff

Last reviewed: 25 August 2026

## Purpose and business outcome

Customer Support Assistant turns a support request into a validated,
classified, prioritized, evidence-grounded response draft with a persistent
audit record. It is intended to reduce manual triage and knowledge-search time,
improve response consistency, surface urgent work earlier, and preserve human
ownership of customer communication and escalation.

The in-product User Guide explains the business problem, AvantiQ solution,
expected value, intended users, inputs and outputs, demo journey, controls, and
automation boundaries.

## Current implementation

- Workflow: `customer_support_triage`
- Adapter: AvantiQ native workflow runtime
- Nodes: `intake -> classify -> knowledge -> respond -> persist`
- API: FastAPI
- Persistence: use-case-owned PostgreSQL database `customer_support`
- Live model: Azure OpenAI, used only for response composition when
  `LIVE_LLM_ENABLED=true`
- Tracing: a dedicated Customer Support Langfuse project
- Admin integration: registration, heartbeat, and sanitized workflow telemetry
- Ticket identity: UI and API fallback generate `CS-XXXXXXXX` identifiers;
  callers may still provide an existing identifier for compatibility
- Local dashboard: <http://127.0.0.1:8030/ui/>
- Local User Guide: <http://127.0.0.1:8030/ui/guide.html>
- Azure dashboard: <https://support.20.235.211.237.sslip.io/ui/>
- Azure API docs: <https://support.20.235.211.237.sslip.io/docs>

## How AvantiQ Core is used

This repository is an application layer over the `avantiq-core` framework; it
does not copy or fork framework code.

| AvantiQ Core capability | Use in this application |
|---|---|
| `bootstrap()` and registry | Registers agents, prompts, tools, and the workflow definition during composition. |
| Native workflow runtime | Executes the five sequential nodes and passes structured results between them. |
| `PromptTemplate` | Defines reviewable prompt contracts, including the grounded response-composition prompt. |
| Provider abstraction | Invokes the configured Azure OpenAI deployment without embedding provider clients in business agents. |
| Runtime controls | Applies configured retry, timeout, concurrency, rate-limit, and cache behavior. |
| Observability | Correlates workflow IDs, request IDs, Langfuse traces, token usage, cost, and sanitized Admin events. |
| Admin client | Registers the manifest, advertises the public dashboard URL, sends heartbeats, and fails open if Admin is unavailable. |
| Shared contracts | Keeps workflow requests, responses, agent profiles, tools, and manifest data compatible with the platform. |

The use case owns ticket rules, support knowledge, classification, response
constraints, persistence, API contracts, UI, and tests. AvantiQ Core owns the
generic orchestration, provider, telemetry, configuration, and platform
integration contracts.

## Data flow and boundaries

1. The dashboard prepares a read-only `CS-XXXXXXXX` ticket ID. FastAPI validates
   supplied identifiers or generates the same format when an API caller omits
   it, then validates the subject, message, customer tier, and caller context.
2. Intake normalizes the request.
3. Classification applies deterministic category and priority policy.
4. The knowledge tool retrieves approved, versioned guidance.
5. The response agent deterministically formats a response or, in live mode,
   asks Azure OpenAI to compose text using only the approved evidence.
6. The persistence tool writes the completed case to PostgreSQL.
7. The API returns the result and publishes sanitized operational telemetry.

Customer messages, knowledge payloads, and generated responses remain inside
the use-case boundary. Admin receives operational metadata, not business
payloads. The assistant drafts decision support; it does not contact customers,
modify accounts, or execute service actions.

## Main endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health/` | Liveness |
| `GET /health/ready` | Readiness |
| `POST /support/triage` | Execute the support workflow |
| `GET /cases/{case_id}` | Retrieve one persisted case |
| `GET /api/cases` | Search and page workflow history |
| `GET /api/cases/trends` | Return dashboard trend data |
| `GET /api/ui-config` | Return safe browser configuration |
| `GET /ui/` | Workflow dashboard |
| `GET /ui/guide.html` | Client-facing User Guide |

## Configuration ownership

Secrets belong in local `.env` files or Azure Key Vault and must never be
committed:

- `AZURE_OPENAI_API_KEY`
- `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`
- `DATABASE_URL`
- `AVANTIQ_ADMIN_CLIENT_TOKEN`, if Admin authentication is enabled

Non-secret runtime values belong in `.env` locally and the AKS ConfigMap in
Azure: provider endpoint/deployment/version, Langfuse URLs, retry/backoff,
workflow timeout and concurrency, rate limit/cache, database pool controls, and
Admin service/public URLs.

`AVANTIQ_ADMIN_CLIENT_SERVICE_BASE_URL` is the cluster-reachable address used
for health monitoring. `AVANTIQ_ADMIN_CLIENT_PUBLIC_BASE_URL` is the
browser-reachable HTTPS origin used for dashboard, guide, OpenAPI, and Swagger
links.

## Local operation

From `C:\workspace-new\avantiq-repo`:

```powershell
docker compose -f deployment\demo\compose.yaml up -d --build `
  customer-support-db-provision customer-support-assistant
docker compose -f deployment\demo\compose.yaml ps customer-support-assistant
```

Verify:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8030/health/ready
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8030/ui/guide.html
```

The shared local PostgreSQL listener is `localhost:5433`. Obtain credentials
from the uncommitted platform demo environment file.

## Azure DEV operation

- Resource group: `rg-avantiq-platform-dev`
- AKS namespace: `avantiq`
- Deployment/service/ingress: `customer-support-assistant`
- ACR repository: `customer-support-assistant`
- Replica count: one economical DEV replica
- SSO: Microsoft Entra through the platform ingress perimeter
- Secrets: Azure Key Vault through the platform CSI configuration
- Database: `customer_support`

Deploy immutable images only. A normal application release builds an image tag
from the use-case commit, updates the deployment image, waits for rollout, and
checks readiness, UI, guide, Admin registration, and recent logs. Do not recreate
PostgreSQL or rotate secrets for a UI/documentation-only release.

## Testing and release gates

```powershell
python -m pytest -q
python -m compileall customer_support_assistant tests
python -m pip check
git diff --check
```

The tests cover deterministic agents, workflow execution, API contracts,
persistence, dashboard assets, User Guide content, Admin onboarding, and
sanitized telemetry. Live provider calls are not required for deterministic
CI.

## Observability and investigation

- Use the application history for business-result review.
- Use Admin workflow runs for status, duration, token/cost, and correlation IDs.
- Use the dedicated Langfuse project for approved trace inspection.
- Check pod logs for provider, database, registration, or readiness errors.
- Keep `LANGFUSE_CAPTURE_LLM_IO=false` unless full prompt/response retention is
  explicitly approved.

## Current release evidence

The 25 August 2026 automatic-ticket-ID release is synchronized to Azure DevOps
and GitHub at application commit `b190254`. Azure Container Registry run
`cu14` published immutable image
`customer-support-assistant:b19025405d7c58c1f3e43e1f161017e5aff1c46b-core-96c9a8d`
with digest
`sha256:fcf435f5d465fa2b9d07bd44741d67f3a4bd981285477ced6a61136ca3b5dd00`.
The AKS deployment reached `1/1 Ready` with zero restarts. In-pod checks
confirmed ready health, the read-only ticket field, and a generated
`CS-XXXXXXXX` value. The public dashboard and User Guide retained the expected
Entra/OAuth2 HTTP 302 boundary. All 18 deterministic tests and compile checks
passed before release.

## Rollback

Set the AKS deployment back to the previous immutable ACR tag and wait for the
rollout. Do not roll back or delete the PostgreSQL database for an application
rollback. If the model provider is the issue, set `LIVE_LLM_ENABLED=false` to
retain deterministic classification, knowledge retrieval, response formatting,
and persistence.

## Handoff checklist

- Confirm the branch is clean and both Azure DevOps and GitHub contain the same
  commit.
- Record the deployed immutable image tag.
- Verify local and Azure User Guide links.
- Verify one deterministic workflow and its persisted result.
- Confirm a dashboard run displays and persists a unique `CS-XXXXXXXX` ticket
  ID and a request without `ticket_id` receives a server-generated ID.
- Confirm Admin health and public links use the intended environment.
- Confirm secrets remain only in `.env`/Key Vault and each Langfuse project is
  use-case specific.
- Record known provider, database, or operational limitations before transfer.
