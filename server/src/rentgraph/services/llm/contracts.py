"""条款抽取的共享工具：正则、归一化、grounding 防幻觉、确定性条款切分。

来源：一期 `services/extract.py` 原样搬运（CLAUSE_HEAD_RE / cn_to_int / _classify /
mock_extract / canon_type / finalize / grounding_ok），语义未改动，二期新增
`norm_text` / `locate` / `FIELD_LABELS` / `span_of` 供 mock 与真实模型两条路径共用后置校验。
"""

import re

from .models import ClauseData, ClauseExtraction
from .prompts import CLAUSE_PROMPT
from .provider import LLMError, provider_mode, structured_call

CLAUSE_HEAD_RE = re.compile(r"第([一二三四五六七八九十百零〇\d]+)条")
SEGMENT_RE = re.compile(r"(?=第[一二三四五六七八九十百零〇\d]+条)")
AMOUNT_RE = re.compile(r"(?:人民币)?([\d,，.]+)\s*元")
MONTHS_RE = re.compile(r"([一二两三四五六七八九十\d]+)\s*(?:个?月|倍)")
DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")

_CN = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

# 字段 → 中文名（契约 §4.2：missing 用中文字段名，前端确认面板同口径）
FIELD_LABELS: dict[str, str] = {
    "name": "名称",
    "region": "区域",
    "address": "地址",
    "rent": "租金",
    "deposit": "押金/付款方式",
    "agency_fee": "中介费",
    "property_fee": "物业费",
    "property_bear": "物业费承担方",
    "net_fee": "网络费",
    "other_fee": "其他费用",
    "area": "面积",
    "layout": "户型",
    "floor": "楼层",
    "orientation": "朝向",
    "bathroom": "独立卫浴",
    "lighting": "采光",
    "furniture": "家具家电",
    "commute_min": "通勤时间",
    "commute_mode": "通勤方式",
    "metro": "地铁",
    "nearby": "周边配套",
    "pet": "宠物",
    "shared": "整租/合租",
    "sublet": "转租",
    "max_people": "入住人数上限",
    "lease_req": "租期要求",
    "available": "可入住时间",
    "notes": "备注",
}


def cn_to_int(s: str) -> int | None:
    """中文数字转整数（条号/倍数），百位以上不猜，返回 None"""
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
    ("违约金", "违约金"), ("押金", "押金"), ("保证金", "押金"),
    ("续租", "续租"), ("续约", "续租"), ("自动续", "续租"),
    ("维修", "维修"), ("修缮", "维修"),
    ("解除", "解约"), ("解约", "解约"), ("退租", "解约"), ("转租", "转租"),
    ("租金", "租金"), ("租赁期", "租期"), ("租期", "租期"),
]

_TITLE_KEYS = [
    ("违约责任", "违约金"), ("解除", "解约"), ("押金", "押金"), ("续租", "续租"),
    ("维修", "维修"), ("转租", "转租"), ("租金", "租金"), ("期限", "租期"),
]

_TITLE_STOP = re.compile(r"[\s：:，,。；;（(【\[]")


def _classify(seg: str) -> str:
    # 先看条名（标题区），避免"合同解除…押金不退"被押金关键词劫持；再回退全文
    title = seg[:16]
    for title_key, canon in _TITLE_KEYS:
        if title_key in title:
            return canon
    for key, canon in _TYPE_KEYS:
        if key in seg:
            return canon
    return "其他"


def _extract_months(seg: str) -> int | None:
    m = re.search(r"([一二两三四五六七八九十\d]+)\s*倍", seg) or re.search(
        r"([一二两三四五六七八九十\d]+)\s*个月", seg
    )
    return cn_to_int(m.group(1)) if m else None


def _iso_date(m: re.Match[str]) -> str:
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def _party_liable(seg: str) -> str | None:
    if "双方" in seg or "任何一方" in seg:
        return "双方"
    if "乙方" in seg:
        return "乙方"
    if "甲方" in seg:
        return "甲方"
    return None


def _title_of(head: str, rest: str) -> str:
    """条名：取条号后到第一个分隔符为止的短标题（「第二条 租赁房屋」），无条名则只留条号"""
    label = _TITLE_STOP.split(rest.strip(), 1)[0][:12]
    return f"{head} {label}" if label else head


def mock_extract(text: str) -> list[ClauseData]:
    """确定性条款切分（mock 路径与单元测试用）：按「第 N 条」切段，原文逐字保留"""
    out: list[ClauseData] = []
    for seg in SEGMENT_RE.split(text):
        seg = seg.strip()
        head = CLAUSE_HEAD_RE.match(seg)
        if not seg or not head:
            continue
        no = cn_to_int(head.group(1))
        amount_m = AMOUNT_RE.search(seg)
        dates = [m for m in DATE_RE.finditer(seg)]
        out.append(
            ClauseData(
                clause_no=no,
                clause_type=_classify(seg),
                title=_title_of(head.group(0), seg[head.end():]),
                text=seg,
                amount=float(amount_m.group(1).replace(",", "").replace("，", "")) if amount_m else None,
                months=_extract_months(seg),
                date_from=_iso_date(dates[0]) if dates else None,
                date_to=_iso_date(dates[-1]) if len(dates) > 1 else None,
                party_liable=_party_liable(seg),
            )
        )
    return out


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
    """统一 mock/LLM 输出：类型归一化 + months/amount 从原文回填（模型漏填也不丢信息）"""
    for c in clauses:
        c.clause_type = canon_type(c.clause_type)
        if c.months is None:
            c.months = _extract_months(c.text)
        if c.amount is None:
            m = AMOUNT_RE.search(c.text)
            c.amount = float(m.group(1).replace(",", "").replace("，", "")) if m else None
    return clauses


def norm_text(s: str) -> str:
    """归一化：去掉全部空白。定位与 grounding 比对都在归一化文本上进行，避免换行/缩进误判"""
    return re.sub(r"\s+", "", s)


def locate(source: str, target: str) -> int | None:
    """在归一化后的 source 中定位 target，返回起始偏移；定位不到返回 None（幻觉信号）"""
    idx = norm_text(source).find(norm_text(target))
    return idx if idx >= 0 else None


def grounding_ok(clauses: list[ClauseData], contract_text: str) -> list[ClauseData]:
    """条款原文必须能在合同全文中定位（防幻觉），压缩空白后比对"""
    compact = norm_text(contract_text)
    return [c for c in clauses if norm_text(c.text) in compact]


def page_of(offset: int, pages: list[str]) -> int | None:
    """按分页文本长度累加定位页码；偏移超出分页范围时不猜页码，返回 None"""
    acc = 0
    for i, page in enumerate(pages, start=1):
        acc += len(norm_text(page))
        if offset < acc:
            return i
    return None


def _with_span(clause: ClauseData, text: str, pages: list[str] | None) -> ClauseData:
    start = locate(text, clause.text)
    if start is None:
        return clause
    clause.char_start = start
    clause.char_end = start + len(norm_text(clause.text))
    if pages is not None:
        clause.page = page_of(start, pages)
    return clause


async def extract_clauses(text: str, pages: list[str] | None = None) -> ClauseExtraction:
    """条款抽取统一入口。0 条命中 → LLMError("NO_CLAUSES")，不做静默空结果返回"""
    if not text.strip():
        raise LLMError("EMPTY_INPUT", "没有可解析的合同文本")
    if provider_mode() == "mock":
        clauses = finalize(mock_extract(text))
    else:
        extracted = await structured_call(ClauseExtraction, CLAUSE_PROMPT + text[:12000])
        clauses = finalize(list(extracted.clauses))
        if not clauses:
            raise LLMError("EMPTY_EXTRACTION", "模型未抽取到任何条款，请确认提交的是完整合同文本")
    grounded = grounding_ok(clauses, text)
    dropped = len(clauses) - len(grounded)
    if not grounded:
        raise LLMError(
            "NO_CLAUSES",
            "未识别到任何条款（文本可能缺少「第 N 条」结构或不是合同正文）",
            hint="请粘贴完整合同文本后重试",
        )
    return ClauseExtraction(
        clauses=[_with_span(c, text, pages) for c in grounded],
        dropped=dropped,
    )
