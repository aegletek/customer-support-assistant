import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from typing import Protocol

from orbit_core import BaseTool, ToolMetadata, ToolResponse
from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, Text, create_engine, desc, func, insert, or_, select
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

    def list_cases(self, *, search: str, page: int, page_size: int) -> tuple[list[dict], int]: ...

    def trend(self, *, days: int = 14) -> list[dict]: ...


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

    def list_cases(self, *, search: str, page: int, page_size: int) -> tuple[list[dict], int]:
        cases = list(self._cases.values())
        if search:
            needle = search.lower()
            cases = [case for case in cases if needle in str(case).lower()]
        cases.sort(key=lambda case: case["created_at"], reverse=True)
        return deepcopy(cases[(page - 1) * page_size:page * page_size]), len(cases)

    def trend(self, *, days: int = 14) -> list[dict]:
        counts: dict[str, int] = {}
        for case in self._cases.values():
            key = str(case["created_at"])[:10]
            counts[key] = counts.get(key, 0) + 1
        return [{"date": key, "runs": value} for key, value in sorted(counts.items())[-days:]]


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

    def list_cases(self, *, search: str, page: int, page_size: int) -> tuple[list[dict], int]:
        filters = []
        if search:
            pattern = f"%{search.lower()}%"
            filters.append(or_(
                func.lower(self.cases.c.ticket_id).like(pattern),
                func.lower(self.cases.c.classification).like(pattern),
                func.lower(self.cases.c.priority).like(pattern),
                func.lower(self.cases.c.workflow_id).like(pattern),
            ))
        query = select(self.cases).order_by(desc(self.cases.c.created_at))
        count = select(func.count()).select_from(self.cases)
        if filters:
            query, count = query.where(*filters), count.where(*filters)
        with self.engine.connect() as connection:
            total = int(connection.execute(count).scalar_one())
            rows = connection.execute(query.offset((page - 1) * page_size).limit(page_size)).mappings().all()
        return [self.get(str(row["case_id"])) for row in rows], total

    def trend(self, *, days: int = 14) -> list[dict]:
        with self.engine.connect() as connection:
            dates = connection.execute(select(self.cases.c.created_at)).scalars().all()
        counts: dict[str, int] = {}
        for date in dates:
            key = date.date().isoformat()
            counts[key] = counts.get(key, 0) + 1
        return [{"date": key, "runs": value} for key, value in sorted(counts.items())[-days:]]


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
