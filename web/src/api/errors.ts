/**
 * 统一错误解释：orval 生成的 fetch 客户端在非 2xx 时抛 `Error & { info, status }`
 * （见 orval.config.ts 的 fetch.forceSuccessResponse），这里把后端 detail 翻成人话。
 */

export interface ApiError {
  status: number;
  code: string;
  message: string;
  /** 需要引导用户改走粘贴时为 true */
  needsPaste?: boolean;
}

const CODE_HINTS: Record<string, string> = {
  NO_TEXT_LAYER:
    "这份 PDF 没有文字层（疑似扫描件/拍照件），请在输入框直接粘贴合同文本；扫描件 OCR 二期上线。",
  TEXT_TOO_SHORT:
    "提取到的文字太少，可能不是完整合同。请重新上传或直接粘贴合同全文。",
  NO_CLAUSES:
    "没识别出「第 N 条」结构的条款，无法出风险报告。请粘贴带条号的完整合同正文。",
  LLM_UNAVAILABLE:
    "条款抽取模型暂时不可用，本次分析已中止（不会给出未经模型抽取的报告）。请稍后重试。",
  LLM_NOT_CONFIGURED:
    "后端未配置模型：请填 server/.env 的 LLM_API_KEY，或设 LLM_PROVIDER=mock 后再演示。",
  LLM_PROVIDER_UNKNOWN: "后端 LLM_PROVIDER 取值非法（只支持 mock | openai）。",
  EMPTY_EXTRACTION: "模型没有抽取到条款，请确认提交的是完整合同文本。",
  NOT_FOUND: "合同不存在或已被清理。",
  ANALYZE_FAILED: "分析中断，请重试或换一份合同。",
};

const detailOf = (info: unknown): unknown => {
  if (!info || typeof info !== "object") return info;
  const payload = info as Record<string, unknown>;
  return "detail" in payload ? payload.detail : payload;
};

export function toApiError(err: unknown, fallback = "请求失败"): ApiError {
  const e = (err ?? {}) as Error & { info?: unknown; status?: number };
  const status = typeof e.status === "number" ? e.status : 0;
  const detail = detailOf(e.info);

  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const d = detail as Record<string, unknown>;
    const code = typeof d.code === "string" ? d.code : "";
    const raw = typeof d.message === "string" ? d.message : "";
    if (code || raw) {
      return {
        status,
        code: code || "ERROR",
        message: CODE_HINTS[code] ?? raw ?? fallback,
        needsPaste: code === "NO_TEXT_LAYER",
      };
    }
  }

  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string; loc?: unknown[] } | undefined;
    const msg = first?.msg
      ? String(first.msg).replace(/^Value error,\s*/, "")
      : fallback;
    return {
      status,
      code: "VALIDATION",
      message: msg.length < 140 ? msg : fallback,
    };
  }

  if (typeof detail === "string" && detail) {
    return {
      status,
      code: e.message || String(status),
      message: CODE_HINTS[detail] ?? detail,
    };
  }

  const raw = e.message || "";
  for (const [code, hint] of Object.entries(CODE_HINTS))
    if (raw.includes(code)) return { status, code, message: hint };
  return {
    status,
    code: raw || "NETWORK",
    message: status
      ? fallback
      : "后端未连通：cd server && .venv/bin/uvicorn rentgraph.main:app --port 8010",
  };
}

export const codeHint = (
  code: string | undefined | null,
  fallback = "请求失败",
) => (code && CODE_HINTS[code]) || fallback;

/** SSE error 事件里的 {code, message} → 统一成 ApiError（message 优先用后端原文） */
export function fromSseError(data: {
  code?: string;
  message?: string;
}): ApiError {
  const code = data.code ?? "ANALYZE_FAILED";
  return {
    status: 200,
    code,
    message: data.message || codeHint(code),
    needsPaste: code === "NO_TEXT_LAYER",
  };
}

export const errorMessage = (err: unknown, fallback?: string) =>
  toApiError(err, fallback).message;
