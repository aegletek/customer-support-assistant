from contextlib import asynccontextmanager
from datetime import datetime
import json
from pathlib import Path
import time
from typing import Any, Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from orbit_core import WorkflowRequest
from orbit_core.admin import AdminOnboarding, AdminWorkflowTelemetry, CostSource
from orbit_core.api.documentation import mount_documentation_pages

from .composition import UseCaseApplication, WORKFLOW_NAME, build_application
from .domain import generate_ticket_id, guardrail_safe_uuid
from .onboarding import build_admin_onboarding


class SupportTriageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: str | None = Field(default=None, min_length=1, max_length=64)
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=5000)
    customer_tier: Literal["standard", "silver", "gold", "platinum"] = "standard"
    user_id: str = Field(default="support-api", min_length=1, max_length=120)
    conversation_id: str = Field(default="support-api", min_length=1, max_length=120)


class SupportCaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    ticket_id: str
    subject: str = ""
    message: str = ""
    customer_tier: str = "standard"
    classification: str
    priority: str
    classification_reason: str
    knowledge_citations: list[Any]
    recommended_response: str
    workflow_id: str
    request_id: str
    created_at: datetime


class SupportCaseListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SupportCaseResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class WorkflowTrendPoint(BaseModel):
    day: str
    runs: int


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
    documentation_root = Path.cwd()
    mount_documentation_pages(app, {
        "readme": ("Customer Support Assistant README", documentation_root / "README.md"),
        "handoff": ("Customer Support Assistant Operational Handoff", documentation_root / "HANDOFF.md"),
    })
    ui_directory = Path(__file__).resolve().parent / "ui"
    app.mount("/ui", StaticFiles(directory=ui_directory, html=True), name="ui")

    @app.get("/", include_in_schema=False)
    async def dashboard_redirect():
        return RedirectResponse(url="/ui/")

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

    @app.get("/api/ui-config")
    async def ui_config():
        return {"langfuse_project_url": application.settings.langfuse_project_url}

    @app.post("/support/triage", response_model=SupportCaseResponse)
    async def triage(request: SupportTriageRequest):
        provided_ticket_id = request.ticket_id.strip() if request.ticket_id else ""
        ticket_id = provided_ticket_id or generate_ticket_id()
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
            input=json.dumps({
                "ticket_id": ticket_id,
                "subject": request.subject,
                "message": request.message,
                "customer_tier": request.customer_tier,
            }),
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
            cost_source=CostSource(response.cost_source),
            pricing_version=response.pricing_version,
            error_code=None if response.success else "workflow_failed",
            model_routes=response.model_routes,
            fallback_used=response.fallback_used,
            fallback_reason=response.fallback_reason,
            safety_checked_count=response.safety_checked_count,
            safety_blocked_count=response.safety_blocked_count,
            safety_error_count=response.safety_error_count,
            safety_max_severity=response.safety_max_severity,
            prompt_attack_detected=response.prompt_attack_detected,
            model_usage=response.model_usage,
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

    @app.get("/cases/{case_id}", response_model=SupportCaseResponse)
    async def case(case_id: UUID):
        stored = application.repository.get(str(case_id))
        if stored is None:
            raise HTTPException(status_code=404, detail="Support case not found")
        return _case_response(stored)

    @app.get("/api/cases", response_model=SupportCaseListResponse)
    async def cases(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=10, ge=1, le=50),
        search: str | None = Query(default=None, max_length=100),
    ):
        stored_cases, total = application.repository.list_cases(
            page=page,
            page_size=page_size,
            search=search,
        )
        return SupportCaseListResponse(
            items=[_case_response(stored) for stored in stored_cases],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=max(1, (total + page_size - 1) // page_size),
        )

    @app.get("/api/cases/trends", response_model=list[WorkflowTrendPoint])
    async def case_trends(days: int = Query(default=14, ge=7, le=90)):
        return application.repository.trends(days=days)

    return app
