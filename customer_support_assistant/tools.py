import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Protocol

from avantiq_core import (
    BaseTool,
    ToolMetadata,
    ToolResponse,
    database_engine_options,
    get_settings,
)
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    insert,
    inspect,
    or_,
    select,
    text,
)
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

    def list_cases(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
    ) -> tuple[list[dict], int]: ...

    def trends(self, *, days: int) -> list[dict]: ...


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

    def list_cases(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
    ) -> tuple[list[dict], int]:
        search_term = (search or "").strip().lower()
        cases = sorted(
            self._cases.values(),
            key=lambda item: (item["created_at"], item["case_id"]),
            reverse=True,
        )
        if search_term:
            searchable_fields = (
                "case_id",
                "ticket_id",
                "subject",
                "message",
                "customer_tier",
                "classification",
                "priority",
                "workflow_id",
                "request_id",
                "recommended_response",
            )
            cases = [
                item
                for item in cases
                if any(
                    search_term in str(item.get(field, "")).lower()
                    for field in searchable_fields
                )
            ]
        offset = (page - 1) * page_size
        return deepcopy(cases[offset:offset + page_size]), len(cases)

    def trends(self, *, days: int) -> list[dict]:
        first_day = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
        counts: dict[str, int] = {}
        for item in self._cases.values():
            created_at = datetime.fromisoformat(str(item["created_at"]))
            day = created_at.date().isoformat()
            if created_at.date() >= first_day:
                counts[day] = counts.get(day, 0) + 1
        return [
            {
                "day": (first_day + timedelta(days=index)).isoformat(),
                "runs": counts.get(
                    (first_day + timedelta(days=index)).isoformat(),
                    0,
                ),
            }
            for index in range(days)
        ]


class CustomerSupportCaseRepository:
    """Durable customer-support case storage owned by this application."""

    def __init__(self, database_url: str | None = None, engine: Engine | None = None) -> None:
        if engine is None and not database_url:
            raise ValueError("DATABASE_URL is required for case persistence")
        self.engine = engine or create_engine(
            database_url,
            **database_engine_options(get_settings(), database_url),
        )
        self.metadata = MetaData()
        self.cases = Table(
            "customer_support_cases",
            self.metadata,
            Column("case_id", String(36), primary_key=True),
            Column("ticket_id", String(64), nullable=False),
            Column("subject", String(200), nullable=True),
            Column("message", Text, nullable=True),
            Column("customer_tier", String(32), nullable=True),
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
        self._ensure_dashboard_columns()

    def _ensure_dashboard_columns(self) -> None:
        """Add input-history fields for databases created before the dashboard."""
        existing = {
            column["name"]
            for column in inspect(self.engine).get_columns("customer_support_cases")
        }
        definitions = {
            "subject": "VARCHAR(200)",
            "message": "TEXT",
            "customer_tier": "VARCHAR(32)",
        }
        missing = [
            (name, definition)
            for name, definition in definitions.items()
            if name not in existing
        ]
        if not missing:
            return
        with self.engine.begin() as connection:
            for name, definition in missing:
                connection.execute(text(
                    f"ALTER TABLE customer_support_cases ADD COLUMN {name} {definition}"
                ))

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
        stored["subject"] = stored.get("subject") or ""
        stored["message"] = stored.get("message") or ""
        stored["customer_tier"] = stored.get("customer_tier") or "standard"
        created_at = stored["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        stored["created_at"] = created_at.isoformat()
        return stored

    def list_cases(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
    ) -> tuple[list[dict], int]:
        offset = (page - 1) * page_size
        filtered_cases = select(self.cases)
        count_cases = select(func.count()).select_from(self.cases)
        search_term = (search or "").strip()
        if search_term:
            pattern = f"%{search_term}%"
            criteria = or_(
                self.cases.c.case_id.ilike(pattern),
                self.cases.c.ticket_id.ilike(pattern),
                self.cases.c.subject.ilike(pattern),
                self.cases.c.message.ilike(pattern),
                self.cases.c.customer_tier.ilike(pattern),
                self.cases.c.classification.ilike(pattern),
                self.cases.c.priority.ilike(pattern),
                self.cases.c.workflow_id.ilike(pattern),
                self.cases.c.request_id.ilike(pattern),
                self.cases.c.recommended_response.ilike(pattern),
            )
            filtered_cases = filtered_cases.where(criteria)
            count_cases = count_cases.where(criteria)
        with self.engine.connect() as connection:
            total = connection.execute(count_cases).scalar_one()
            rows = connection.execute(
                filtered_cases
                .order_by(self.cases.c.created_at.desc(), self.cases.c.case_id.desc())
                .offset(offset)
                .limit(page_size)
            ).mappings().all()
        cases = []
        for row in rows:
            stored = dict(row)
            stored["subject"] = stored.get("subject") or ""
            stored["message"] = stored.get("message") or ""
            stored["customer_tier"] = stored.get("customer_tier") or "standard"
            created_at = stored["created_at"]
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            stored["created_at"] = created_at.isoformat()
            cases.append(stored)
        return cases, int(total)

    def trends(self, *, days: int) -> list[dict]:
        first_day = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
        first_timestamp = datetime.combine(
            first_day,
            datetime.min.time(),
            tzinfo=timezone.utc,
        )
        with self.engine.connect() as connection:
            timestamps = connection.execute(
                select(self.cases.c.created_at).where(
                    self.cases.c.created_at >= first_timestamp
                )
            ).scalars().all()
        counts: dict[str, int] = {}
        for timestamp in timestamps:
            day = timestamp.date().isoformat()
            counts[day] = counts.get(day, 0) + 1
        return [
            {
                "day": (first_day + timedelta(days=index)).isoformat(),
                "runs": counts.get(
                    (first_day + timedelta(days=index)).isoformat(),
                    0,
                ),
            }
            for index in range(days)
        ]


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
