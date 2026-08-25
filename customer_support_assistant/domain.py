from dataclasses import asdict, dataclass
import json
from typing import Any
from uuid import UUID, uuid4


def guardrail_safe_uuid() -> str:
    """Return a UUID that cannot resemble a hyphen-separated payment card."""

    characters = list(uuid4().hex)
    for index in range(0, len(characters), 4):
        characters[index] = "a"
    return str(UUID(hex="".join(characters)))


def generate_ticket_id() -> str:
    """Return a readable, unique AvantiQ customer-support ticket ID."""

    unique_part = uuid4().hex[:8].upper()
    return f"CS-{unique_part}"


@dataclass(slots=True, frozen=True)
class SupportTicket:
    ticket_id: str
    subject: str
    message: str
    customer_tier: str = "standard"

    @classmethod
    def from_workflow_input(cls, value: str) -> "SupportTicket":
        text = value.strip()
        if not text:
            raise ValueError("support ticket input is required")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return cls(
                ticket_id="CLI-REQUEST",
                subject=text,
                message=text,
            )
        if not isinstance(payload, dict):
            raise ValueError("support ticket input must be a JSON object")
        required = ("ticket_id", "subject", "message")
        missing = [name for name in required if not str(payload.get(name, "")).strip()]
        if missing:
            raise ValueError("missing support ticket fields: " + ", ".join(missing))
        return cls(
            ticket_id=str(payload["ticket_id"]).strip(),
            subject=str(payload["subject"]).strip(),
            message=str(payload["message"]).strip(),
            customer_tier=str(payload.get("customer_tier", "standard")).strip().lower()
            or "standard",
        )

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class SupportClassification:
    category: str
    priority: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def classify_ticket(ticket: SupportTicket) -> SupportClassification:
    content = f"{ticket.subject} {ticket.message}".lower()
    if any(term in content for term in ("fraud", "unauthorized", "stolen")):
        category, priority, reason = (
            "account_security",
            "urgent",
            "Potential account-security issue requires immediate review.",
        )
    elif any(term in content for term in ("sign in", "login", "password", "access")):
        category, priority, reason = (
            "account_access",
            "high",
            "Customer cannot access an authenticated account feature.",
        )
    elif any(term in content for term in ("statement", "invoice", "billing", "charge")):
        category, priority, reason = (
            "statements_and_billing",
            "medium",
            "Request concerns a statement or billing document.",
        )
    else:
        category, priority, reason = (
            "general_support",
            "normal",
            "Request does not match a higher-priority support category.",
        )
    if ticket.customer_tier in {"gold", "platinum"} and priority == "medium":
        priority = "high"
        reason += " Priority is elevated for the customer tier."
    return SupportClassification(category, priority, reason)


def result_output(runtime: Any, node_name: str) -> Any:
    result = runtime.state.get("results", {}).get(node_name)
    if result is None:
        raise RuntimeError(f"required workflow result is missing: {node_name}")
    return getattr(result, "output", result)
