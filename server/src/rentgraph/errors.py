"""统一错误模型：所有面向用户的原因都带可执行动作（PRD §9.2 失败必须可重试）。

`AppError` 是后端内部统一异常；`error_from_exception` 把 W1 各层（parsing/llm）的
typed error 映射成同构错误体，避免每个路由重复判断。
"""

from typing import Any

# 错误码 → (HTTP 状态, 默认提示)
KNOWN_CODES: dict[str, tuple[int, str]] = {
    "WORKSPACE_NOT_FOUND": (404, "工作台不存在或已被清理，请新建工作台后重试"),
    "WORKSPACE_EXPIRED": (410, "临时工作台已到期（一期不承诺长期保存），请新建工作台"),
    "NOT_FOUND": (404, "对象不存在或已被删除"),
    "UNSUPPORTED_FORMAT": (415, "请改用 PDF / Word / Excel / 文本文件，或直接粘贴文本"),
    "DOC_UNSUPPORTED": (415, "旧版 .doc 需要先另存为 .docx，或直接粘贴文本"),
    "NO_TEXT_LAYER": (422, "这份 PDF 没有可提取的文字层（疑似扫描件），请粘贴合同文本后重试"),
    "EMPTY_DOCUMENT": (422, "文件里没有解析到内容，请检查文件或改用粘贴"),
    "NO_CLAUSES": (422, "未识别到任何条款（文本可能缺少「第 N 条」结构），请粘贴完整合同文本"),
    "NO_DRAFTS": (422, "未识别到房源信息，请检查文本或改用批量粘贴格式"),
    "TOO_MANY_HOUSES": (422, "候选房源超过 10 套，请拆分批次或先移除部分房源"),
    "INVALID_PREFERENCE": (422, "偏好数值不合法（预算与通勤需为非负数字）"),
    "INVALID_STATE": (409, "当前状态不允许该操作，请刷新后重试"),
    "CONTEXT_MISSING": (422, "请先选定目标房源或绑定合同后再提问"),
    "LLM_UNAVAILABLE": (503, "模型服务调用失败，请稍后重试（本次未生成任何结论）"),
    "LLM_NOT_CONFIGURED": (503, "未配置模型服务（LLM_API_KEY），当前只能使用演示解析"),
    "LLM_PROVIDER_UNKNOWN": (500, "模型提供方配置不正确"),
    "ANALYZE_FAILED": (500, "解析或核验中断，请重试"),
    "RUN_CANCELLED": (409, "本次任务已取消"),
}


class AppError(Exception):
    """带机器可读 code 的业务异常。"""

    def __init__(self, code: str, message: str | None = None, hint: str | None = None) -> None:
        self.code = code
        status, default_hint = KNOWN_CODES.get(code, (400, ""))
        self.status = status
        self.message = message or code
        self.hint = hint if hint is not None else default_hint
        super().__init__(f"{code}: {self.message}")


def error_body(exc: BaseException) -> dict[str, Any]:
    """把任意异常转成 {code, message, hint}（不泄漏堆栈给前端）。"""

    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None)
    hint = getattr(exc, "hint", None)
    if isinstance(code, str) and isinstance(message, str):
        return {"code": code, "message": message, "hint": hint or ""}
    if isinstance(exc, AppError):
        return {"code": exc.code, "message": exc.message, "hint": exc.hint}
    return {"code": "INTERNAL_ERROR", "message": f"服务异常：{type(exc).__name__}", "hint": "请稍后重试或刷新页面"}


def http_status(exc: BaseException) -> int:
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        return status
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code in KNOWN_CODES:
        return KNOWN_CODES[code][0]
    return 500
