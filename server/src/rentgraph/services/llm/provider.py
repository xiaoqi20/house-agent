"""LLM 提供方选择与结构化调用（契约 §1）。

LLM_PROVIDER=mock → 全程确定性实现（测试与演示）；openai → 百炼 qwen。
未知取值一律报 LLM_PROVIDER_UNKNOWN：**绝不**从 openai 静默回退到 mock，
否则用户会拿到一份正则伪造的「抽取成功」（PRD：抽取失败不要假装成功）。
"""

from typing import Any, Literal, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from ...config import settings

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """LLM 契约层统一错误：带 code，直接透传给 SSE error 事件与前端提示"""

    def __init__(self, code: str, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


def provider_mode() -> Literal["mock", "openai"]:
    """唯一的 provider 选择点：所有 llm/ 模块都走这里，避免出现两套判断口径"""
    if settings.llm_provider == "mock":
        return "mock"
    if settings.llm_provider == "openai":
        return "openai"
    raise LLMError(
        "LLM_PROVIDER_UNKNOWN",
        f"未知 LLM_PROVIDER={settings.llm_provider}（可选 mock | openai）",
        hint="检查 server/.env 的 LLM_PROVIDER，缺失时默认 mock",
    )


def llm_available() -> bool:
    """健康检查用：mock 恒定可用（确定性实现）；openai 需要 API key"""
    if settings.llm_provider == "mock":
        return True
    if settings.llm_provider == "openai":
        return bool(settings.llm_api_key)
    return False


def get_chat_model() -> BaseChatModel:
    """真实模型客户端。抽取/问答都是检索型任务，一律关思考（enable_thinking=False）"""
    mode = provider_mode()
    if mode == "mock":
        raise LLMError("LLM_PROVIDER_MOCK", "当前 LLM_PROVIDER=mock，不应调用真实模型")
    if not settings.llm_api_key:
        raise LLMError(
            "LLM_NOT_CONFIGURED",
            "LLM_PROVIDER=openai 但未读到 LLM_API_KEY",
            hint="检查 server/.env 配置",
        )
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=0,
        timeout=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
        extra_body={"enable_thinking": False},
    )


def with_schema(model: BaseChatModel, schema: type[T]) -> Runnable[Any, T]:
    """结构化输出：Pydantic 模型 + with_structured_output（契约 §1）"""
    return model.with_structured_output(schema)


async def structured_call(schema: type[T], prompt: str) -> T:
    """按 schema 调真实模型。任何失败都抛带 code 的 LLMError，绝不返回正则/mock 结果"""
    try:
        chain = with_schema(get_chat_model(), schema)
        return await chain.ainvoke(prompt)
    except LLMError:
        raise
    except Exception as exc:  # 网络/限流/JSON 解析失败统一收敛，避免上层拿到半成品
        raise LLMError(
            "LLM_UNAVAILABLE",
            f"模型调用失败：{type(exc).__name__}: {str(exc)[:180]}",
            hint="检查 LLM_BASE_URL / LLM_API_KEY 与模型可用性后重试",
        ) from exc
