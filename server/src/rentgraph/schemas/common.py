"""通用响应模型：错误体、运行状态。"""

from typing import Any, Literal

from pydantic import BaseModel, Field

RunStatusLiteral = Literal["queued", "running", "interrupted", "done", "failed", "cancelled"]


class ErrorBody(BaseModel):
    """统一错误体：前端按 code 决定引导文案（如 NO_TEXT_LAYER → 提示粘贴）。"""

    code: str = Field(description="机器可读错误码")
    message: str = Field(description="给用户看的原因")
    hint: str = Field(default="", description="可执行的重试/替代动作")


class ErrorOut(BaseModel):
    error: ErrorBody


class RunOut(BaseModel):
    id: str
    kind: str
    status: RunStatusLiteral = "queued"
    workspace_id: str | None = None
    thread_id: str | None = None
    progress: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: ErrorBody | None = None


class OkOut(BaseModel):
    ok: bool = True
