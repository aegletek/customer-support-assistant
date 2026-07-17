import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from typing import Protocol

from augent_core import BaseTool, ToolMetadata, ToolResponse
from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, Text, create_engine, insert, select
from sqlalchemy.engine import Engine

from .domain import guardrail_safe_uuid


KNOWLEDGE_BASE = {
    "account_access": [
        {
            "article_id": "KB-ACCESS-001",
            "title": "Restore access to authenticated account features",
            "citation": "support://knowledge/KB-ACCESS-001",
            "guidance": "Verify the customer session, refresh account permissions, and retry.",
        }
    ],
    "account_security": [
        {
            "article_id": "KB-SECURITY-001",
            "title": "Escalate suspected account compromise",
            "citation": "support://knowledge/KB-SECURITY-001",
            "guidance": "Secure the account and route the case to the fraud response queue.",
        }
    ],
    "statements_and_billing": [
        {
            "article_id": "KB-BILLING-001",
            "title": "Troubleshoot missing statements",
            "citation": "support://knowledge/KB-BILLING-001",
            "guidance": "Confirm the statement period and refresh document availability.",
        }
    ],
    "general_support": [
        {
            "article_id": "KB-GENERAL-001",
            "title": "General support triage",
            "citation": "support://knowledge/KB-GENERAL-001",
            "guidance": "Confirm the request and route it to the appropriate support queue.",
        }
    ],
}


class SupportKnowledgeTool(BaseTool):
    """Search the versioned, application-owned demonstration knowledge base."""

    def __init__(self) -> None:
        super().__init__(ToolMetadata(
            name="support_knowledge",
            description="Returns approved support guidance for a classified ticket.",
            capabilities=["support_knowledge"],
        ))

    async def execute(self, runtime) -> ToolResponse:
        request = runtime.state["tool_request"]
        category = str(request.parameters.get("category", "")).strip()
        if not category:
            return ToolResponse(success=False, error="category is required")
        articles = KNOWLEDGE_BASE.get(category, KNOWLEDGE_BASE["general_support"])
        return ToolResponse(
            success=True,
            data={"category": category, "articles": deepcopy(articles)},
        )


class CaseRepository(Protocol):
    def save(self, payload: dict) -> dict: ...

    def get(self, case_id: str) -> dict | None: ...


class InMemoryCaseRepository:
    """Deterministic test boundary replaced by PostgreSQL in a later phase."""

    def __init__(self) -> None:
        self._cases: dict[str, dict] = {}

    def save(self, payload: dict) -> dict:
        stored = deepcopy(payload)
        stored["case_id"] = guardrail_safe_uuid()
        stored["created_at"] = datetime.now(timezone.utc).isoformat()
        self._cases[stored["case_id"]] = stored
        return deepcopy(stored)

    def get(self, case_id: str) -> dict | None:
        stored = self._cases.get(case_id)
        return deepcopy(stored) if stored is not None else None


class CustomerSupportCaseRepository:
    """Durable customer-support case storage owned by this application."""

    def __init__(self, database_url: str | None = None, engine: Engine | None = None) -> None:
        if engine is None and not database_url:
            raise ValueError("DATABASE_URL is required for case persistence")
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)
        self.metadata = MetaData()
        self.cases = Table(
            "customer_support_cases",
            self.metadata,
            Column("case_id", String(36), primary_key=True),
            Column("ticket_id", String(64), nullable=False),
            Column("classification", String(120), nullable=False),
            Column("priority", String(32), nullable=False),
            Column("classification_reason", Text, nullable=False),
            Column("knowledge_citations", JSON, nullable=False),
            Column("recommended_response", Text, nullable=False),
            Column("workflow_id", String(64), nullable=False),
            Column("request_id", String(64), nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )
        self.metadata.create_all(self.engine)

    def save(self, payload: dict) -> dict:
        case_id = guardrail_safe_uuid()
        created_at = datetime.now(timezone.utc)
        stored = {
            **deepcopy(payload),
            "case_id": case_id,
            "created_at": created_at,
        }
        with self.engine.begin() as connection:
            connection.execute(insert(self.cases).values(**stored))
        return {**stored, "created_at": created_at.isoformat()}

    def get(self, case_id: str) -> dict | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(self.cases).where(self.cases.c.case_id == case_id)
            ).mappings().first()
        if row is None:
            return None
        stored = dict(row)
        created_at = stored["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        stored["created_at"] = created_at.isoformat()
        return stored


class CasePersistenceTool(BaseTool):
    def __init__(self, repository: CaseRepository) -> None:
        super().__init__(ToolMetadata(
            name="case_persistence",
            description="Stores the completed support case behind an application boundary.",
            capabilities=["case_persistence"],
        ))
        self.repository = repository

    async def execute(self, runtime) -> ToolResponse:
        request = runtime.state["tool_request"]
        case = request.parameters.get("case")
        if not isinstance(case, dict):
            return ToolResponse(success=False, error="case is required")
        try:
            stored = await asyncio.to_thread(self.repository.save, case)
            return ToolResponse(success=True, data=stored)
        except Exception:
            return ToolResponse(success=False, error="Case persistence failed")
