from dataclasses import dataclass
from pathlib import Path
from typing import Any

from augent_core import PromptTemplate, bootstrap, reload_settings

from .agents import AGENTS
from .config import UseCaseSettings, load_environment
from .tools import ExampleLookupTool


WORKFLOW_NAME = "usecase_workflow"


@dataclass(slots=True)
class UseCaseApplication:
    runtime: Any
    settings: UseCaseSettings


PROMPTS = (
    PromptTemplate(
        name="usecase_intake",
        description="Collect approved data for the request.",
        template="Collect approved data for: {{ question }}",
    ),
    PromptTemplate(
        name="usecase_response",
        description="Create the final use-case response.",
        template="Summarize this verified result: {{ previous_output }}",
    ),
)


def build_application(
    settings: UseCaseSettings | None = None,
    *,
    example_tool: ExampleLookupTool | None = None,
) -> UseCaseApplication:
    load_environment()
    reload_settings()
    settings = settings or UseCaseSettings()
    example_tool = example_tool or ExampleLookupTool()

    def configure(registry):
        for agent in AGENTS:
            registry.agent(agent)
        for prompt in PROMPTS:
            registry.prompt(prompt)
        registry.tool(example_tool)
        registry.workflow(WORKFLOW_NAME, Path(__file__).with_name("workflow.yaml"))

    return UseCaseApplication(
        runtime=bootstrap(configure).runtime(),
        settings=settings,
    )
