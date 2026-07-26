import json

from orbit_core import (
    ChatRequest,
    ToolRequest,
    UserMessage,
    WorkerAgent,
    WorkerProfile,
)

from .domain import SupportTicket, classify_ticket, result_output


class IntakeAgent(WorkerAgent):
    profile = WorkerProfile(
        capability="support_intake",
        prompt_template="support_intake",
    )

    async def process(self, runtime):
        return SupportTicket.from_workflow_input(
            runtime.prompt_variables["question"]
        ).as_dict()


class ClassifyAgent(WorkerAgent):
    profile = WorkerProfile(
        capability="support_classification",
        prompt_template="support_classification",
    )

    async def process(self, runtime):
        ticket = SupportTicket(**result_output(runtime, "intake"))
        return classify_ticket(ticket).as_dict()


class KnowledgeAgent(WorkerAgent):
    profile = WorkerProfile(
        capability="support_knowledge",
        prompt_template="support_knowledge",
    )

    async def process(self, runtime):
        classification = result_output(runtime, "classify")
        runtime.state["tool_request"] = ToolRequest(
            tool_name="support_knowledge",
            parameters={"category": classification["category"]},
        )
        response = await self.tool_executor.execute("support_knowledge", runtime)
        if not response.success:
            raise RuntimeError(response.error)
        return response.data


class RespondAgent(WorkerAgent):
    profile = WorkerProfile(
        capability="support_response",
        prompt_template="support_response",
    )

    async def process(self, runtime):
        ticket = result_output(runtime, "intake")
        classification = result_output(runtime, "classify")
        knowledge = result_output(runtime, "knowledge")
        articles = knowledge["articles"]
        citations = [article["citation"] for article in articles]
        guidance = " ".join(article["guidance"] for article in articles)
        return {
            "ticket_id": ticket["ticket_id"],
            "classification": classification["category"],
            "priority": classification["priority"],
            "classification_reason": classification["reason"],
            "knowledge_citations": citations,
            "recommended_response": (
                f"We identified this as {classification['category'].replace('_', ' ')}. "
                f"{guidance} We will keep ticket {ticket['ticket_id']} updated."
            ),
        }


class LiveRespondAgent(RespondAgent):
    """Compose only the customer-facing text with the configured live LLM."""

    async def process(self, runtime):
        deterministic = await super().process(runtime)
        llm_response = await self.llm.chat(
            ChatRequest(messages=[UserMessage(content=runtime.state["prompt"])]),
            runtime,
        )
        deterministic["recommended_response"] = llm_response.content.strip()
        return deterministic


class PersistAgent(WorkerAgent):
    profile = WorkerProfile(
        capability="support_persistence",
        prompt_template="support_persistence",
    )

    async def process(self, runtime):
        case = dict(result_output(runtime, "respond"))
        case["workflow_id"] = runtime.workflow.workflow_id
        case["request_id"] = runtime.trace.request_id
        runtime.state["tool_request"] = ToolRequest(
            tool_name="case_persistence",
            parameters={"case": case},
        )
        response = await self.tool_executor.execute("case_persistence", runtime)
        if not response.success:
            raise RuntimeError(response.error)
        return json.dumps(response.data, sort_keys=True)


AGENTS = (IntakeAgent, ClassifyAgent, KnowledgeAgent, RespondAgent, PersistAgent)
