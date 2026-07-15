from augent_core import BaseTool, ToolMetadata, ToolResponse


class ExampleLookupTool(BaseTool):
    """Replace this deterministic example with an injected external client."""

    def __init__(self) -> None:
        super().__init__(ToolMetadata(
            name="example_lookup",
            description="Returns deterministic example data for the requested task.",
            capabilities=["example_lookup"],
        ))

    async def execute(self, runtime) -> ToolResponse:
        request = runtime.state["tool_request"]
        query = str(request.parameters.get("query", "")).strip()
        if not query:
            return ToolResponse(success=False, error="query is required")
        return ToolResponse(
            success=True,
            data={"query": query, "result": f"Verified example data for {query}"},
        )
