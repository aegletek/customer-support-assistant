import json
from pathlib import Path
from decimal import Decimal

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
import yaml

from augent_core import ChatResponse, WorkflowRequest
from augent_core.ai.llm.models import TokenUsage
from customer_support_assistant.api import create_app
from customer_support_assistant.composition import WORKFLOW_NAME, build_application
from customer_support_assistant.config import UseCaseSettings
from customer_support_assistant.domain import (
    SupportTicket,
    classify_ticket,
    guardrail_safe_uuid,
)
from customer_support_assistant.tools import (
    CustomerSupportCaseRepository,
    InMemoryCaseRepository,
    SupportKnowledgeTool,
)


TICKET = {
    "ticket_id": "DEMO-1001",
    "subject": "Unable to access monthly statement",
    "message": "My July statement does not appear after I sign in.",
    "customer_tier": "gold",
}


class FakeProvider:
    def __init__(self):
        self.prompts = []

    async def chat(self, request):
        self.prompts.append(request.messages[0].content)
        return ChatResponse(
            content=(
                "We understand you cannot access your monthly statement. "
                "Please sign out, sign in again, and check the Statements area. "
                "We will keep ticket DEMO-1001 updated."
            ),
            model="deterministic-test-model",
            finish_reason="stop",
            usage=TokenUsage(
                prompt_tokens=20,
                completion_tokens=15,
                total_tokens=35,
            ),
            provider_cost=Decimal("0.002"),
        )


def build_test_application():
    return build_application(
        UseCaseSettings(
            _env_file=None,
            database_url="test-only",
            live_llm_enabled=False,
        ),
        repository=InMemoryCaseRepository(),
    )


class FakeOnboarding:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.events = []
        self.manifest = type(
            "Manifest",
            (),
            {
                "id": "customer-support-assistant",
                "runtime": type("Runtime", (), {"environment": "test"})(),
            },
        )()

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    def submit_telemetry(self, event):
        self.events.append(event)


@pytest.mark.asyncio
async def test_workflow_executes_end_to_end():
    application = build_test_application()

    response = await application.runtime.execute(WorkflowRequest(
        workflow=WORKFLOW_NAME,
        input=json.dumps(TICKET),
        user_id="test-user",
        conversation_id="test-conversation",
        workflow_id=guardrail_safe_uuid(),
        request_id=guardrail_safe_uuid(),
        correlation_id=guardrail_safe_uuid(),
    ))

    assert response.success is True
    result = json.loads(response.output)
    assert result["ticket_id"] == "DEMO-1001"
    assert result["classification"] == "account_access"
    assert result["priority"] == "high"
    assert result["knowledge_citations"] == ["support://knowledge/KB-ACCESS-001"]
    assert result["workflow_id"] == response.workflow_id
    assert application.repository.get(result["case_id"]) == result


@pytest.mark.asyncio
async def test_live_response_uses_llm_without_changing_routing_or_citations():
    provider = FakeProvider()
    application = build_application(
        UseCaseSettings(
            _env_file=None,
            live_llm_enabled=True,
            database_url="test-only",
            openrouter_api_key="",
            openrouter_model="",
            langfuse_public_key="",
            langfuse_secret_key="",
        ),
        llm_provider=provider,
        repository=InMemoryCaseRepository(),
    )

    response = await application.runtime.execute(WorkflowRequest(
        workflow=WORKFLOW_NAME,
        input=json.dumps(TICKET),
        user_id="test-user",
        conversation_id="test-conversation",
        workflow_id=guardrail_safe_uuid(),
        request_id=guardrail_safe_uuid(),
        correlation_id=guardrail_safe_uuid(),
    ))

    result = json.loads(response.output)
    assert response.success is True
    assert result["classification"] == "account_access"
    assert result["priority"] == "high"
    assert result["knowledge_citations"] == ["support://knowledge/KB-ACCESS-001"]
    assert result["recommended_response"].startswith("We understand")
    assert response.input_tokens == 20
    assert response.output_tokens == 15
    assert response.cost_amount == Decimal("0.002")
    assert "Approved knowledge" in provider.prompts[0]


def test_live_response_requires_provider_and_langfuse_configuration() -> None:
    settings = UseCaseSettings(
        _env_file=None,
        live_llm_enabled=True,
        database_url="test-only",
        openrouter_api_key="",
        openrouter_model="",
        langfuse_public_key="",
        langfuse_secret_key="",
    )

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        settings.require_live_llm()


def test_api_health_triage_and_case_retrieval():
    application = build_test_application()
    onboarding = FakeOnboarding()
    with TestClient(create_app(application, onboarding=onboarding)) as client:
        health = client.get("/health/")
        readiness = client.get("/health/ready")
        response = client.post("/support/triage", json={
            **TICKET,
            "user_id": "test-user",
            "conversation_id": "test-conversation",
        })
        payload = response.json()
        stored = client.get(f"/cases/{payload['case_id']}")
        missing = client.get("/cases/00000000-0000-0000-0000-000000000000")
        legacy = client.post("/execute", json={"task": "legacy"})
        assert onboarding.started is True

    assert onboarding.stopped is True
    assert [event.event_type.value for event in onboarding.events] == [
        "workflow.started",
        "workflow.completed",
    ]
    assert onboarding.events[-1].payload.usage.total_tokens == 0
    assert onboarding.events[-1].payload.cost.source.value == "unavailable"
    assert onboarding.events[-1].payload.cost.amount is None
    assert health.status_code == 200
    assert health.json() == {
        "status": "healthy",
        "service": "customer-support-assistant",
    }
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "ready"
    assert response.status_code == 200
    assert payload["ticket_id"] == "DEMO-1001"
    assert payload["classification"] == "account_access"
    assert payload["priority"] == "high"
    assert payload["knowledge_citations"] == ["support://knowledge/KB-ACCESS-001"]
    assert "prompt" not in payload
    assert "tool_request" not in payload
    assert stored.status_code == 200
    assert stored.json() == payload
    assert missing.status_code == 404
    assert legacy.status_code == 404


def test_api_rejects_invalid_or_unknown_ticket_fields() -> None:
    with TestClient(create_app(build_test_application())) as client:
        empty_message = client.post("/support/triage", json={**TICKET, "message": ""})
        unknown_field = client.post(
            "/support/triage",
            json={**TICKET, "internal_prompt": "must not be accepted"},
        )

    assert empty_message.status_code == 422
    assert unknown_field.status_code == 422


def test_openapi_exposes_only_approved_business_paths() -> None:
    with TestClient(create_app(build_test_application())) as client:
        paths = client.get("/openapi.json").json()["paths"]

    assert "/health/" in paths
    assert "/health/ready" in paths
    assert "/support/triage" in paths
    assert "/cases/{case_id}" in paths
    assert "/execute" not in paths


@pytest.mark.asyncio
async def test_knowledge_tool_rejects_empty_category():
    class Runtime:
        state = {
            "tool_request": type("Request", (), {"parameters": {"category": "  "}})()
        }

    response = await SupportKnowledgeTool().execute(Runtime())

    assert response.success is False
    assert response.error == "category is required"


def test_classification_policy_prioritizes_account_access() -> None:
    classification = classify_ticket(SupportTicket(**TICKET))

    assert classification.category == "account_access"
    assert classification.priority == "high"


def test_workflow_declares_five_native_nodes() -> None:
    workflow_path = Path(__file__).parents[1] / "customer_support_assistant" / "workflow.yaml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))["workflow"]

    assert workflow["execution_adapter"] == "native"
    assert [node["name"] for node in workflow["nodes"]] == [
        "intake",
        "classify",
        "knowledge",
        "respond",
        "persist",
    ]


def test_sql_repository_round_trips_readable_case() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    repository = CustomerSupportCaseRepository(engine=engine)
    payload = {
        "ticket_id": "DEMO-DB-1",
        "classification": "account_access",
        "priority": "high",
        "classification_reason": "Customer cannot access the account.",
        "knowledge_citations": ["support://knowledge/KB-ACCESS-001"],
        "recommended_response": "Verify the session and retry.",
        "workflow_id": "workflow-1",
        "request_id": "request-1",
    }

    stored = repository.save(payload)

    assert repository.get(stored["case_id"]) == stored
    assert isinstance(stored["knowledge_citations"], list)


def test_default_application_requires_database_configuration() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        build_application(
            UseCaseSettings(
                _env_file=None,
                database_url="",
                live_llm_enabled=False,
            )
        )


def test_generated_identifiers_do_not_match_payment_card_pattern() -> None:
    from augent_core.guardrails.policies.pii_guard import PIIGuard

    identifier = guardrail_safe_uuid()

    assert PIIGuard._patterns["payment_card"].search(identifier) is None
