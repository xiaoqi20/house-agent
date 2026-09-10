"""表格型输入（Excel / CSV 转成的「表头: 值 | 表头: 值」行）→ 房源草稿。

为什么单独一层：`mock` 路径原本只认自由文本（必须含「元/月」「分钟」），
Excel 导入的文件行因此被整行丢弃（PRD §3.1 明确要求支持 .xlsx/.xls/.csv）。
这里是纯确定性映射：列名语义固定，每个字段的证据就是它所在的那一行原文。
"""

from __future__ import annotations

import re
from typing import Any

from .contracts import FIELD_LABELS
from .models import ListingDraft

# 列名 → 房源字段（同一字段允许多种写法，按长度从长到短匹配，避免「租金」吃掉「物业费租金」）
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("房源名称", "小区名称", "小区", "名称", "房源", "楼盘", "标题"),
    "region": ("所在区域", "区域", "行政区", "商圈"),
    "address": ("详细地址", "地址", "门牌"),
    "rent": ("月租金", "租金", "月租", "价格"),
    "deposit": ("押金方式", "押付方式", "付款方式", "支付方式", "押付", "押金"),
    "agency_fee": ("中介费",),
    "property_fee": ("物业费",),
    "property_bear": ("物业费承担方", "物业费承担", "物业承担方"),
    "net_fee": ("网络费", "网费", "宽带费"),
    "other_fee": ("其他费用", "其他费"),
    "area": ("建筑面积", "面积", "平米", "㎡"),
    "layout": ("户型", "房型"),
    "floor": ("楼层", "所在楼层"),
    "orientation": ("朝向", "采光朝向"),
    "bathroom": ("独立卫浴", "独卫", "卫浴"),
    "lighting": ("采光",),
    "furniture": ("家具家电", "家具", "家电", "配置"),
    "commute_min": ("通勤时间", "通勤", "通勤分钟"),
    "commute_mode": ("通勤方式", "交通方式"),
    "metro": ("最近地铁", "地铁", "地铁站"),
    "nearby": ("周边配套", "周边", "配套"),
    "pet": ("宠物", "养宠"),
    "shared": ("整租合租", "租赁方式", "合租整租", "出租方式"),
    "sublet": ("转租",),
    "max_people": ("入住人数上限", "人数上限", "限住人数", "入住人数"),
    "lease_req": ("租期要求", "租期", "最短租期"),
    "available": ("可入住时间", "入住时间", "起租时间"),
    "notes": ("备注", "说明"),
}

_INT_FIELDS = {"rent", "agency_fee", "property_fee", "net_fee", "commute_min", "max_people"}
_BOOL_FIELDS = {"bathroom", "shared"}
_NAME_PREFIX_RE = re.compile(r"^\s*(?:房源\s*[A-Za-z0-9一二三四五六]?|第\s*\d+\s*套)[：:、.\s-]*")
_PAIR_RE = re.compile(r"\s*([^:|：]+?)\s*[:：]\s*([^|]*)")


def _pairs(line: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in _PAIR_RE.findall(line):
        key = key.strip()
        value = value.strip()
        if key and key not in out:
            out[key] = value
    return out


def _field_of(column: str) -> str | None:
    for field, aliases in COLUMN_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if column == alias:
                return field
    for field, aliases in COLUMN_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if alias in column:
                return field
    return None


def _to_int(value: str) -> int | None:
    match = re.search(r"(\d[\d,]*)", value.replace("，", ","))
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _to_float(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)", value)
    return float(match.group(1)) if match else None


def _to_bool(value: str) -> bool | None:
    if re.search(r"是|有|独立|支持|可以|允许|true|Y", value, re.IGNORECASE):
        return True
    if re.search(r"否|无|没有|不支持|不可以|禁止|false|N", value, re.IGNORECASE):
        return False
    if re.search(r"合租|次卧|主卧|床位|单间", value):
        return True
    if re.search(r"整租|开间|一居|两居|三居", value):
        return False
    return None


_BULLET_RE = re.compile(r"^\s*(?:[-*+]\s*|#{1,6}\s*|\d+[.、)]\s*)+")


def _records(text: str) -> list[tuple[str | None, str]]:
    """把文本切成记录：

    - 一行里有 ≥2 个「表头: 值」→ 这一行本身就是一条记录（Excel / CSV 行）；
    - 一行只有 1 个键值 → 按空行/标题分组（Markdown 分段清单），标题作为名称提示。
    """

    normalized = text.replace("｜", "|").replace("　", " ")
    records: list[tuple[str | None, str]] = []
    hint: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer, hint
        if buffer:
            records.append((hint, " | ".join(buffer)))
        buffer, hint = [], None

    for raw_line in normalized.splitlines():
        line = _BULLET_RE.sub("", raw_line.strip()).strip()
        if not line:
            flush()
            continue
        pairs = _pairs(line)
        if not pairs:
            flush()
            hint = line  # 标题行：开启一个新分节
            continue
        if hint is None:
            records.append((None, line))  # 无标题上下文：一行一条记录（Excel/CSV）
            continue
        buffer.append(line)  # 有标题：该行属于这个分节
    flush()
    return records


def table_rows_to_drafts(text: str, source: str = "file-xlsx", limit: int = 10) -> list[ListingDraft]:
    """把表格 / 清单文本解析成草稿；识别不到可用行时返回空列表（调用方回退自由文本正则）。"""

    drafts: list[ListingDraft] = []
    for hint, line in _records(text):
        pairs = _pairs(line)
        if len(pairs) < 2:
            continue
        values: dict[str, Any] = {}
        evidence: dict[str, str] = {}
        for column, raw in pairs.items():
            field = _field_of(column)
            if field is None or not raw:
                continue
            if field == "commute_min" and "分钟" not in raw and ("号线" in raw or "米" in raw):
                continue  # 位置描述不是通勤分钟数（宁缺勿错）
            if field in _INT_FIELDS:
                parsed: Any = _to_int(raw)
            elif field in _BOOL_FIELDS:
                parsed = _to_bool(raw)
            elif field == "area":
                parsed = _to_float(raw)
            else:
                parsed = raw
            if parsed is None or parsed == "":
                continue
            values[field] = parsed
            evidence[field] = raw
        if values.get("rent") is None:
            continue
        if not values.get("name"):
            if hint:
                cleaned = re.sub(_NAME_PREFIX_RE, "", hint)
                values["name"] = cleaned[:18]
                evidence["name"] = hint
            else:
                fallback = (values.get("region") or "") + (values.get("layout") or "")
                values["name"] = fallback or f"房源 {len(drafts) + 1}"
        if "deposit" in values:
            evidence.setdefault("deposit", str(values["deposit"]))
        drafts.append(
            ListingDraft(
                source=source,  # type: ignore[arg-type]
                raw=line,
                evidence=evidence,
                missing=[label for field, label in FIELD_LABELS.items() if values.get(field) is None],
                **values,
            )
        )
        if len(drafts) >= limit:
            break
    return drafts


__all__ = ["COLUMN_ALIASES", "table_rows_to_drafts"]
