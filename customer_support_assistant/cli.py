import argparse
import asyncio

from augent_core import WorkflowRequest

from .composition import WORKFLOW_NAME, build_application


async def run(task: str) -> str:
    application = build_application()
    response = await application.runtime.execute(WorkflowRequest(
        workflow=WORKFLOW_NAME,
        input=task,
        user_id="usecase-cli",
        conversation_id="usecase-cli",
    ))
    if not response.success:
        raise RuntimeError(response.error)
    return response.output


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Customer Support Assistant")
    parser.add_argument("--task", required=True)
    args = parser.parse_args()
    print(asyncio.run(run(args.task)))


if __name__ == "__main__":
    main()
