from augent_core import ToolRequest, WorkerAgent, WorkerProfile


class IntakeAgent(WorkerAgent):
    profile = WorkerProfile(
        capability="usecase_intake",
        prompt_template="usecase_intake",
    )

    async def process(self, runtime):
        runtime.state["tool_request"] = ToolRequest(
            tool_name="example_lookup",
            parameters={"query": runtime.prompt_variables["question"]},
        )
        response = await self.tool_executor.execute("example_lookup", runtime)
        if not response.success:
            raise RuntimeError(response.error)
        return response.data


class ResponseAgent(WorkerAgent):
    profile = WorkerProfile(
        capability="usecase_response",
        prompt_template="usecase_response",
    )

    async def process(self, runtime):
        return f"Augent Use Case completed: {runtime.state['prompt']}"


AGENTS = (IntakeAgent, ResponseAgent)
