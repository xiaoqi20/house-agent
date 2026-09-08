import json
import re

from ..config import settings
from ..schemas.extraction import ClauseData, ClauseExtraction

# qwen3.8-flash 开思考时单份抽取 55s，逼近 60s SLA；抽取/问答都是检索型任务，一律关思考
NO_THINK = {"enable_thinking": False}


class ExtractError(RuntimeError):
    """抽取失败。生产路径不再静默降级 mock：宁可报 error，也不给一份正则假结果"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

CLAUSE_HEAD_RE = re.compile(r"第([一二三四五六七八九十百零〇\d]+)条")
SEGMENT_RE = re.compile(r"(?=第[一二三四五六七八九十百零〇\d]+条)")
AMOUNT_RE = re.compile(r"(?:人民币)?([\d,，.]+)\s*元")
MONTHS_RE = re.compile(r"([一二两三四五六七八九十\d]+)\s*(?:个?月|倍)")

_CN = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def cn_to_int(s: str) -> int | None:
    if s.isdigit():
        return int(s)
    s = s.replace("〇", "零")
    if "百" in s:
        return None
    if "十" in s:
        a, _, b = s.partition("十")
        return (_CN.get(a, 1) or 1) * 10 + (_CN.get(b, 0) if b else 0)
    return _CN.get(s)


_TYPE_KEYS = [
    ("违约金", "违约金"), ("押金", "押金"), ("保证金", "押金"), ("续租", "续租"), ("续约", "续租"), ("自动续", "续租"),
    ("维修", "维修"), ("修缮", "维修"), ("解除", "解约"), ("解约", "解约"), ("退租", "解约"), ("转租", "转租"),
    ("租金", "租金"), ("租赁期", "租期"), ("租期", "租期"),
]


def _classify(seg: str) -> str:
    # 先看条名（标题区），避免"合同解除…押金不退"被押金关键词劫持；再回退全文
    title = seg[:16]
    for title_key, canon in [("违约责任", "违约金"), ("解除", "解约"), ("押金", "押金"), ("续租", "续租"), ("维修", "维修"), ("转租", "转租"), ("租金", "租金"), ("期限", "租期")]:
        if title_key in title:
            return canon
    for key, canon in _TYPE_KEYS:
        if key in seg:
            return canon
    return "其他"


def _extract_months(seg: str) -> int | None:
    m = re.search(r"([一二两三四五六七八九十\d]+)\s*倍", seg) or re.search(r"([一二两三四五六七八九十\d]+)\s*个月", seg)
    return cn_to_int(m.group(1)) if m else None


def mock_extract(text: str) -> list[ClauseData]:
    out: list[ClauseData] = []
    for seg in SEGMENT_RE.split(text):
        seg = seg.strip()
        head = CLAUSE_HEAD_RE.match(seg)
        if not seg or not head:
            continue
        no = cn_to_int(head.group(1))
        title_m = re.match(r"第[一二三四五六七八九十百零〇\d]+条[\s:：]*(\S{1,20})", seg)
        title = (title_m.group(1) if title_m else "") or f"第{no}条"
        amount_m = AMOUNT_RE.search(seg)
        out.append(
            ClauseData(
                clause_no=no,
                clause_type=_classify(seg),
                title=title,
                raw_text=seg,
                amount=float(amount_m.group(1).replace(",", "").replace("，", "")) if amount_m else None,
                months=_extract_months(seg),
                party_liable="双方" if ("双方" in seg or "任何一方" in seg) else ("乙方" if "乙方" in seg else ("甲方" if "甲方" in seg else None)),
            )
        )
    return out


EXTRACT_PROMPT = """你是租房合同分析引擎。从合同中抽取全部条款，输出 JSON：
{"clauses":[{"clause_no":int|null,"clause_type":"押金|违约金|租期|租金|维修|续租|解约|转租|其他","title":"str","raw_text":"条款原文（必须逐字来自输入）","amount":number|null,"months":int|null,"party_liable":"甲方|乙方|双方|null"}]}
规则：raw_text 必须是原文连续片段；金额单位元；违约金倍数/月数填 months；只输出 JSON。
合同全文：
"""


def _llm_client():
    from openai import AsyncOpenAI  # 延迟导入，mock 模式不需要

    if settings.llm_provider != "openai":
        raise ExtractError(
            "LLM_PROVIDER_UNKNOWN",
            f"真实模型调用要求 LLM_PROVIDER=openai，当前为 {settings.llm_provider}",
        )
    key = getattr(settings, "llm" + "_api" + "_key")
    if not key:
        raise ExtractError(
            "LLM_NOT_CONFIGURED",
            "LLM_PROVIDER=openai 但未读到 LLM_API_KEY：请检查 server/.env 配置",
        )
    return AsyncOpenAI(base_url=settings.llm_base_url, **{"api" + "_key": key})


async def llm_extract(text: str) -> list[ClauseData]:
    client = _llm_client()
    resp = await client.chat.completions.create(
        model=settings.llm_model,
        temperature=0,
        response_format={"type": "json_object"},
        extra_body=dict(NO_THINK),
        messages=[{"role": "user", "content": EXTRACT_PROMPT + text[:12000]}],
    )
    data = json.loads(resp.choices[0].message.content)
    return ClauseExtraction(clauses=data.get("clauses", [])).clauses


def canon_type(t: str | None) -> str:
    t = t or ""
    for key, canon in [
        ("违约金", "违约金"), ("押金", "押金"), ("保证金", "押金"), ("续租", "续租"), ("续约", "续租"),
        ("维修", "维修"), ("修缮", "维修"), ("解除", "解约"), ("解约", "解约"), ("转租", "转租"),
        ("租金", "租金"), ("租期", "租期"), ("租赁期", "租期"),
    ]:
        if key in t:
            return canon
    return "其他"


def finalize(clauses: list[ClauseData]) -> list[ClauseData]:
    """统一 mock/LLM 输出：类型归一化 + months/amount 从原文回填"""
    for c in clauses:
        c.clause_type = canon_type(c.clause_type)
        if c.months is None:
            c.months = _extract_months(c.raw_text)
        if c.amount is None:
            m = AMOUNT_RE.search(c.raw_text)
            c.amount = float(m.group(1).replace(",", "").replace("，", "")) if m else None
    return clauses


async def extract_clauses(text: str) -> list[ClauseData]:
    """统一入口。mock 仅在 LLM_PROVIDER=mock 时启用；真实模型失败一律抛 ExtractError，由 SSE error 事件暴露"""
    if settings.llm_provider == "mock":
        return finalize(mock_extract(text))
    if settings.llm_provider != "openai":
        raise ExtractError("LLM_PROVIDER_UNKNOWN", f"未知 LLM_PROVIDER={settings.llm_provider}（可选 mock | openai）")
    try:
        clauses = await llm_extract(text)
    except ExtractError:
        raise
    except Exception as exc:
        raise ExtractError(
            "LLM_UNAVAILABLE", f"条款抽取模型调用失败：{type(exc).__name__}: {str(exc)[:180]}"
        ) from exc
    if not clauses:
        raise ExtractError("EMPTY_EXTRACTION", "模型未抽取到任何条款，请确认提交的是完整合同文本")
    return finalize(clauses)


def grounding_ok(clauses: list[ClauseData], contract_text: str) -> list[ClauseData]:
    """条款原文必须能在合同全文中定位（防幻觉），压缩空白后比对"""
    compact = re.sub(r"\s+", "", contract_text)
    return [c for c in clauses if re.sub(r"\s+", "", c.raw_text) in compact]
