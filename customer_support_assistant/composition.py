from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orbit_core import PromptTemplate, bootstrap, reload_settings

from .agents import AGENTS, LiveRespondAgent, RespondAgent
from .config import UseCaseSettings, load_environment
from .tools import (
    CasePersistenceTool,
    CaseRepository,
    CustomerSupportCaseRepository,
    SupportKnowledgeTool,
)


WORKFLOW_NAME = "customer_support_triage"


@dataclass(slots=True)
class UseCaseApplication:
    runtime: Any
    settings: UseCaseSettings
    repository: CaseRepository


PROMPTS = (
    PromptTemplate(
        name="support_intake",
        description="Validate and normalize the incoming support ticket.",
        template="Validate this support ticket: {{ question }}",
    ),
    PromptTemplate(
        name="support_classification",
        description="Classify the support ticket using deterministic policy.",
        template="Classify this validated ticket: {{ results.intake }}",
    ),
    PromptTemplate(
        name="support_knowledge",
        description="Retrieve approved guidance for the classification.",
        template="Find approved guidance for: {{ results.classify }}",
    ),
    PromptTemplate(
        name="support_response",
        description="Compose a response from approved support guidance.",
        template=(
            "You are a customer support response assistant. Draft a concise, empathetic "
            "customer-facing response. Use only the approved guidance and citations below. "
            "Do not invent policies, resolution times, account facts, or actions already taken. "
            "Do not expose internal classification reasoning. Mention the ticket ID and give "
            "clear next steps.\n\n"
            "Ticket: {{ results.intake }}\n"
            "Classification: {{ results.classify }}\n"
            "Approved knowledge: {{ results.knowledge }}"
        ),
    ),
    PromptTemplate(
        name="support_persistence",
        description="Persist the completed support result.",
        template="Persist this support result: {{ results.respond }}",
    ),
)


def build_application(
    settings: UseCaseSettings | None = None,
    *,
    llm_provider: object | None = None,
    knowledge_tool: SupportKnowledgeTool | None = None,
    repository: CaseRepository | None = None,
) -> UseCaseApplication:
    load_environment()
    reload_settings()
    settings = settings or UseCaseSettings()
    knowledge_tool = knowledge_tool or SupportKnowledgeTool()
    if repository is None:
        settings.require_database()
        repository = CustomerSupportCaseRepository(settings.database_url)
    if llm_provider is None:
        settings.require_live_llm()

    agents = tuple(
        LiveRespondAgent
        if agent is RespondAgent and settings.live_llm_enabled
        else agent
        for agent in AGENTS
    )

    def configure(registry):
        if llm_provider is not None:
            registry.llm_provider(llm_provider)
        for agent in agents:
            registry.agent(agent)
        for prompt in PROMPTS:
            registry.prompt(prompt)
        registry.tool(knowledge_tool)
        registry.tool(CasePersistenceTool(repository))
        registry.workflow(WORKFLOW_NAME, Path(__file__).with_name("workflow.yaml"))

    return UseCaseApplication(
        runtime=bootstrap(configure).runtime(),
        settings=settings,
        repository=repository,
    )
