from fastapi.testclient import TestClient
import pytest

from augent_core import WorkflowRequest
from augent_usecase.api import create_app
from augent_usecase.composition import WORKFLOW_NAME, build_application
from augent_usecase.tools import ExampleLookupTool


@pytest.mark.asyncio
async def test_workflow_executes_end_to_end():
    application = build_application()

    response = await application.runtime.execute(WorkflowRequest(
        workflow=WORKFLOW_NAME,
        input="Review customer C-100",
        user_id="test-user",
        conversation_id="test-conversation",
    ))

    assert response.success is True
    assert response.output.startswith("Augent Use Case completed:")
    assert "Verified example data for Review customer C-100" in response.output


def test_api_health_and_execute():
    with TestClient(create_app(build_application())) as client:
        health = client.get("/health")
        response = client.post("/execute", json={"task": "Review customer C-100"})

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_example_tool_rejects_empty_query():
    class Runtime:
        state = {
            "tool_request": type("Request", (), {"parameters": {"query": "  "}})()
        }

    response = await ExampleLookupTool().execute(Runtime())

    assert response.success is False
    assert response.error == "query is required"
