from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from augent_core import WorkflowRequest

from .composition import UseCaseApplication, WORKFLOW_NAME, build_application


class ExecuteRequest(BaseModel):
    task: str = Field(min_length=1)
    user_id: str = "usecase-api"
    conversation_id: str = "usecase-api"


def create_app(application: UseCaseApplication | None = None) -> FastAPI:
    application = application or build_application()
    app = FastAPI(title=application.settings.app_name, version="0.1.0")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/execute")
    async def execute(request: ExecuteRequest):
        response = await application.runtime.execute(WorkflowRequest(
            workflow=WORKFLOW_NAME,
            input=request.task,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
        ))
        if not response.success:
            raise HTTPException(status_code=502, detail=response.error)
        return response

    return app
