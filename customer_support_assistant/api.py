from contextlib import asynccontextmanager
from datetime import datetime
import json
from pathlib import Path
import time
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from orbit_core import WorkflowRequest
from orbit_core.admin import AdminOnboarding, AdminWorkflowTelemetry, CostSource

from .composition import UseCaseApplication, WORKFLOW_NAME, build_application
from .domain import guardrail_safe_uuid
from .onboarding import build_admin_onboarding


class SupportTriageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: str = Field(min_length=1, max_length=64)
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=5000)
    customer_tier: Literal["standard", "silver", "gold", "platinum"] = "standard"
    user_id: str = Field(default="support-api", min_length=1, max_length=120)
    conversation_id: str = Field(default="support-api", min_length=1, max_length=120)


class SupportCaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: UUID
    ticket_id: str
    classification: str
    priority: str
    classification_reason: str
    knowledge_citations: list[str]
    recommended_response: str
    workflow_id: UUID
    request_id: UUID
    created_at: datetime


class CaseHistoryResponse(BaseModel):
    items: list[SupportCaseResponse]
    page: int
    page_size: int
    total: int


def _case_response(payload: dict) -> SupportCaseResponse:
    return SupportCaseResponse.model_validate(payload)


def create_app(
    application: UseCaseApplication | None = None,
    onboarding: AdminOnboarding | None = None,
) -> FastAPI:
    application = application or build_application()
    onboarding = onboarding or build_admin_onboarding()
    telemetry = AdminWorkflowTelemetry(onboarding)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await onboarding.start()
        try:
            yield
        finally:
            await onboarding.stop()

    app = FastAPI(
        title=application.settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health/")
    async def health():
        return {"status": "healthy", "service": "customer-support-assistant"}

    @app.get("/health/ready")
    async def readiness():
        return {
            "status": "ready",
            "service": "customer-support-assistant",
            "version": app.version,
        }

    @app.post("/support/triage", response_model=SupportCaseResponse)
    async def triage(request: SupportTriageRequest):
        workflow_id = guardrail_safe_uuid()
        request_id = guardrail_safe_uuid()
        correlation_id = guardrail_safe_uuid()
        telemetry.started(
            WORKFLOW_NAME,
            workflow_id,
            workflow_id=workflow_id,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        started_at = time.perf_counter()
        response = await application.runtime.execute(WorkflowRequest(
            workflow=WORKFLOW_NAME,
            input=json.dumps(request.model_dump(include={
                "ticket_id",
                "subject",
                "message",
                "customer_tier",
            })),
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            workflow_id=workflow_id,
            request_id=request_id,
            correlation_id=correlation_id,
        ))
        telemetry.finished(
            WORKFLOW_NAME,
            workflow_id,
            succeeded=response.success,
            workflow_id=response.workflow_id,
            request_id=response.request_id,
            correlation_id=response.correlation_id,
            trace_id=response.langfuse_trace_id,
            duration_ms=round((time.perf_counter() - started_at) * 1000),
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cached_input_tokens=response.cached_input_tokens,
            cost_amount=response.cost_amount,
            cost_currency=response.cost_currency,
            cost_source=(
                CostSource.PROVIDER_REPORTED
                if response.cost_amount is not None
                else CostSource.UNAVAILABLE
            ),
            error_code=None if response.success else "workflow_failed",
        )
        if not response.success:
            raise HTTPException(status_code=502, detail="Support workflow failed")
        try:
            return _case_response(json.loads(response.output))
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(
                status_code=500,
                detail="Support workflow returned an invalid result",
            ) from exc

    @app.get("/case-history/trend")
    async def case_trend():
        return {"daily": application.repository.trend()}

    @app.get("/cases/{case_id}", response_model=SupportCaseResponse)
    async def case(case_id: UUID):
        stored = application.repository.get(str(case_id))
        if stored is None:
            raise HTTPException(status_code=404, detail="Support case not found")
        return _case_response(stored)

    @app.get("/cases", response_model=CaseHistoryResponse)
    async def cases(search: str = Query(default="", max_length=120), page: int = Query(default=1, ge=1), page_size: int = Query(default=10, ge=1, le=50)):
        items, total = application.repository.list_cases(search=search, page=page, page_size=page_size)
        return CaseHistoryResponse(items=[_case_response(item) for item in items], page=page, page_size=page_size, total=total)

    @app.get("/ui/config")
    async def ui_config():
        return {"display_name": application.settings.ui_display_name, "langfuse_url": application.settings.langfuse_host}

    app.mount("/ui", StaticFiles(directory=Path(__file__).with_name("ui"), html=True), name="customer-support-ui")

    return app
