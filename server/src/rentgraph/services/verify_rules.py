"""房源承诺 × 合同条款确定性核验（契约 §4.7、PRD §3.3、§10 场景 2）。

只判定可机械判定的项：金额（容差 0）、日期（按天）、枚举（承担方 / 宠物 / 转租 / 合租人数）。
语义类判断（维修责任、口头承诺）不在这里下结论：
- 找不到对应条款 → `未约定`，建议写入补充协议（**禁止**推断为「合同已承诺」）；
- 房源侧缺值或条款表述解析不出 → `无法判断`，提示人工核对原文；
- 冲突 → `severity=high` 且 advice 给出可执行动作（要求修改 / 写回一致版本）；
- 一致 → 说明按约履行。

输出行按重要性排序：冲突 → 未约定 → 无法判断 → 一致，UI 表格第一屏就是待处理项。

输入兼容三形态：ORM 行（`clause_no`/`raw_text`/`page`/`char_start`）、契约里的 dict
（`clause_no`/`text`/`clause_type`/`amount`/`months`/`date_from`）、
前端 `clauses_list` 的 `[no, title, text]` 三元组。
`clause_id` 优先取条款主键 `id`，没有时回退条号（前端「定位合同原文」用的就是条号）。
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from .domain import format_amount, normalise_house, raw_value

RESULTS: tuple[str, ...] = ("一致", "冲突", "未约定", "无法判断")
RESULT_ORDER = {"冲突": 0, "未约定": 1, "无法判断": 2, "一致": 3}
# 冲突必须最高优先级；未约定=要写补充协议，无法判断=需人工核对，一致=无需动作
SEVERITY: dict[str, str | None] = {"冲突": "high", "未约定": "medium", "无法判断": "low", "一致": None}


@dataclass
class VRow:
    """核验表一行：房源承诺 ↔ 合同条款，必须能回到房源字段与合同原文（PRD §3.3）。"""

    field: str
    claim: str
    clause_id: int | None
    clause_text: str
    page: int | None
    char_start: int | None
    result: str
    advice: str
    severity: str | None


# ---------- 条款归一化 ----------

_CN_DIGITS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
_MONEY_RE = re.compile(r"(?:人民币)?\s*([\d,，]+(?:\.\d+)?)\s*元")
_MONTHS_RE = re.compile(
    r"共\s*([一二两三四五六七八九十\d]+)\s*个月|([一二两三四五六七八九十\d]+)\s*个月|([一二两三四五六七八九十\d]+)\s*年"
)
_PAY_RE = re.compile(r"押\s*([一二两三四五六])\s*付\s*([一二两三四五六\d])")
_DATE_FULL_RE = re.compile(r"(\d{4})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*日?")
_DATE_MD_RE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_FORBID_RE = re.compile(r"不得|禁止|不可|不许|严禁|无权")
_ALLOW_RE = re.compile(r"允许|可以|可饲养|同意|可养")
_SUBLET_ALLOW_RE = re.compile(r"可转|允许转|同意转|可以转")
_AREA_RE = re.compile(r"([\d.]+)\s*(?:平方米|平米|平|㎡)")
_PEOPLE_RE = re.compile(
    r"(?:居住人数|入住人数|居住人|同住|不得超过|不超过)\D{0,8}?([一二两三四五六\d]+)\s*人"
)


def _cn_int(text: str) -> int | None:
    if text.isdigit():
        return int(text)
    return _CN_DIGITS.get(text)


def _money(text: str) -> int | float | None:
    match = _MONEY_RE.search(text)
    return _as_number(match.group(1)) if match else None


def _as_number(value: Any) -> int | float | None:
    """金额/数值归一化（'5,800' / '12000' / 12000 均可），非数值返回 None。"""
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        number = float(str(value).replace(",", "").replace("，", ""))
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def _months(text: str) -> int | None:
    """条款/承诺里的月数：共 X 个月 / X 个月 / X 年（未写明月数的日期串不误判）。"""
    for match in _MONTHS_RE.finditer(text):
        for index, group in enumerate(match.groups()):
            if group:
                value = _cn_int(group)
                if value is None:
                    return None
                return value * 12 if index == 2 else value
    return None


def _payment(text: str) -> tuple[int, int] | None:
    """解析「押X付Y」→ (押金月数, 付款周期月数)。"""
    match = _PAY_RE.search(text)
    if not match:
        return None
    deposit, period = _cn_int(match.group(1)), match.group(2)
    if deposit is None:
        return None
    return deposit, (int(period) if period.isdigit() else _CN_DIGITS.get(period, 0))


def _date(value: Any, default_year: int | None = None) -> date | None:
    """解析日期：datetime.date、YYYY 年 M 月 D 日 / YYYY-MM-DD、M 月 D 日（缺年时用 default_year）。"""
    if isinstance(value, date):
        return value
    text = "" if value is None else str(value)
    match = _DATE_FULL_RE.search(text)
    if match:
        return _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    match = _DATE_MD_RE.search(text)
    if match and default_year is not None:
        return _safe_date(default_year, int(match.group(1)), int(match.group(2)))
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _bearer(text: str) -> str | None:
    """承担方：房东（甲方/出租方）或租客（乙方/承租方）。"""
    if re.search(r"乙方|承租方|承租人|租客", text):
        return "租客"
    if re.search(r"甲方|出租方|房东", text):
        return "房东"
    return None


def _house_bearer(text: Any) -> str | None:
    if text is None:
        return None
    value = str(text)
    if any(key in value for key in ("房东", "甲方")):
        return "房东"
    if any(key in value for key in ("租客", "乙方", "自己")):
        return "租客"
    return None


def _clause(raw: Mapping[str, Any] | Sequence[Any] | object) -> dict[str, Any]:
    """条款归一化：支持 ORM 行 / dict / 前端 [no, title, text] 三元组。"""
    if isinstance(raw, (list, tuple)):
        items = list(raw) + [None] * (3 - len(raw))
        no, title, text = items[0], items[1], items[2]
        return {
            "id": _int(no),
            "no": _int(no),
            "title": "" if title is None else str(title),
            "text": "" if text is None else str(text),
            "page": None,
            "char_start": None,
            "clause_type": "",
            "amount": None,
            "months": None,
            "date_from": None,
            "date_to": None,
        }
    text = raw_value(raw, "text", "raw_text", "clause_text", "content")
    date_from = raw_value(raw, "date_from", "dateFrom", "start_date")
    date_to = raw_value(raw, "date_to", "dateTo", "end_date")
    return {
        "id": _int(raw_value(raw, "id", "clause_id")) or _int(raw_value(raw, "clause_no", "no", "clauseNo")),
        "no": _int(raw_value(raw, "clause_no", "no", "clauseNo")),
        "title": str(raw_value(raw, "title") or ""),
        "text": "" if text is None else str(text),
        "page": _int(raw_value(raw, "page")),
        "char_start": _int(raw_value(raw, "char_start", "charStart")),
        "clause_type": str(raw_value(raw, "clause_type", "clauseType", "type") or ""),
        "amount": _as_number(raw_value(raw, "amount")),
        "months": _int(raw_value(raw, "months")),
        "date_from": date_from,
        "date_to": date_to,
    }


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clauses(raw: Sequence[Mapping[str, Any] | Sequence[Any] | object]) -> list[dict[str, Any]]:
    return [_clause(item) for item in raw]


def _blob(clause: dict[str, Any]) -> str:
    return f"{clause['title']} {clause['text']}"


def _find(
    clauses: list[dict[str, Any]],
    *,
    types: Sequence[str] = (),
    keywords: Sequence[str] = (),
    exclude: Sequence[str] = (),
) -> dict[str, Any] | None:
    """定位候选条款：先按 clause_type，再按关键词；exclude 命中即排除（如「违约金」混入「租金」）。"""
    usable = [c for c in clauses if not any(token in _blob(c) for token in exclude)]
    for clause in usable:
        if clause["clause_type"] and clause["clause_type"] in types:
            return clause
    for clause in usable:
        if any(token in _blob(clause) for token in keywords):
            return clause
    return None


def _row(
    field: str,
    claim: str,
    clause: dict[str, Any] | None,
    result: str,
    advice: str,
) -> VRow:
    return VRow(
        field=field,
        claim=claim,
        clause_id=None if clause is None else clause["id"],
        clause_text="未找到对应条款" if clause is None else clause["text"],
        page=None if clause is None else clause["page"],
        char_start=None if clause is None else clause["char_start"],
        result=result,
        advice=advice,
        severity=SEVERITY[result],
    )


# ---------- 逐项比较器 ----------


def _cmp_rent(h: dict[str, Any], clauses: list[dict[str, Any]]) -> VRow:
    field = "租金"
    rent = h["rent"]
    clause = _find(clauses, types=("租金",), keywords=("月租金", "月租", "租金"), exclude=("违约金",))
    claim = f"月租 {format_amount(rent)} 元" if rent is not None else "月租（房源侧未填写）"
    if rent is None:
        return _row(
            field,
            claim,
            clause,
            "无法判断",
            "先与房东确认月租金再核验；合同金额与口头报价不一致时以书面合同为准",
        )
    if clause is None:
        return _row(
            field,
            claim,
            None,
            "未约定",
            "合同未写明月租金：要求在补充协议中写明“月租金为人民币 X 元”与支付周期后再签字",
        )
    amount = _money(clause["text"]) if clause["amount"] is None else clause["amount"]
    if amount is None:
        return _row(
            field,
            claim,
            clause,
            "无法判断",
            "合同租金条款解析不出金额，请人工核对原文并要求写明“月租金为人民币 X 元”",
        )
    if amount == rent:
        return _row(field, claim, clause, "一致", "金额一致，按约履行；付款日期与方式以合同条款为准")
    return _row(
        field,
        claim,
        clause,
        "冲突",
        f"与房东确认沟通价 {format_amount(rent)} 元：要求把合同月租金从 {format_amount(amount)} 元改回 "
        f"{format_amount(rent)} 元，写回一致版本后再签字",
    )


def _cmp_deposit(h: dict[str, Any], clauses: list[dict[str, Any]]) -> VRow:
    field = "押金/付款方式"
    claim_text = "" if h["deposit"] is None else str(h["deposit"]).strip()
    clause = _find(
        clauses,
        types=("押金",),
        keywords=("押金", "付款方式", "支付方式", "押一付", "押二付", "押三付"),
    )
    claim = f"押金/付款方式：{claim_text}" if claim_text else "押金/付款方式（房源侧未填写）"
    if not claim_text:
        return _row(
            field, claim, clause, "无法判断", "先与房东确认押金月数与付款方式，再核对合同押金金额与退还条件"
        )
    claim_pay = _payment(claim_text)
    if claim_pay is None:
        return _row(
            field,
            claim,
            clause,
            "无法判断",
            f"房源侧「{claim_text}」无法解析出押金月数，请确认后按“押X付Y”核对合同条款",
        )
    if clause is None:
        return _row(
            field,
            claim,
            None,
            "未约定",
            "合同未约定押金与付款方式：要求在补充协议中写明“押 X 付 Y、押金金额 Y 元”并约定退还时限",
        )
    clause_pay = _payment(_blob(clause))
    clause_months = clause_pay[0] if clause_pay else clause["months"]
    clause_amount = clause["amount"] if clause["amount"] is not None else _money(clause["text"])
    rent = h["rent"]
    expected = int(rent * claim_pay[0]) if rent is not None else None
    if clause_months is None and clause_amount is None:
        return _row(
            field,
            claim,
            clause,
            "无法判断",
            "合同押金条款未写明押金月数与金额，请人工核对原文并要求写明“押金为 X 个月租金”",
        )
    months_differ = clause_months is not None and clause_months != claim_pay[0]
    amount_differ = clause_amount is not None and expected is not None and clause_amount != expected
    if months_differ or amount_differ:
        if clause_amount is not None and expected is not None:
            gap = f"，押金金额应为 {format_amount(expected)} 元（合同为 {format_amount(clause_amount)} 元）"
            if clause_amount > expected:
                gap += f"，多占用资金 {format_amount(clause_amount - expected)} 元"
        elif rent is not None and clause_months is not None:
            delta = (clause_months - claim_pay[0]) * rent
            gap = (
                f"，押金多占用资金 {format_amount(delta)} 元"
                if delta > 0
                else "，押金占用资金更少需与房东确认原因"
            )
        else:
            gap = ""
        return _row(
            field,
            claim,
            clause,
            "冲突",
            f"要求按「{claim_text}」修改合同押金与支付条款{gap}；押金与付款方式写回一致版本后再支付定金",
        )
    return _row(field, claim, clause, "一致", "与约定一致，按约履行；仍需确认押金退还时限与扣款标准")


def _cmp_property(h: dict[str, Any], clauses: list[dict[str, Any]]) -> VRow:
    field = "物业费"
    bearer = _house_bearer(h["propertyBear"])
    fee = h["propertyFee"]
    clause = _find(clauses, keywords=("物业费", "物业管理费"))
    if bearer and fee is not None:
        claim = f"物业费由{bearer}承担，{format_amount(fee)} 元/月"
    elif bearer:
        claim = f"物业费由{bearer}承担"
    elif fee is not None:
        claim = f"物业费 {format_amount(fee)} 元/月"
    else:
        claim = "物业费（房源侧未填写）"
    if bearer is None and fee is None:
        return _row(
            field,
            claim,
            clause,
            "无法判断",
            "房源侧未记录物业费金额与承担方，先与房东确认再核验合同物业费条款",
        )
    if clause is None:
        return _row(
            field,
            claim,
            None,
            "未约定",
            "合同未约定物业费：要求在补充协议中写明金额、承担方与缴纳方式（随租金或单独缴）",
        )
    clause_bearer = _bearer(clause["text"])
    clause_amount = clause["amount"] if clause["amount"] is not None else _money(clause["text"])
    if clause_amount is None and clause_bearer is None:
        return _row(field, claim, clause, "无法判断", "合同物业费条款解析不出金额与承担方，请人工核对原文")
    if bearer and clause_bearer and bearer != clause_bearer:
        return _row(
            field,
            claim,
            clause,
            "冲突",
            f"口头承诺与合同冲突（合同为{clause_bearer}承担）：要求在签约前把物业费条款改为“物业费由{bearer}承担”，"
            "或按合同金额从月租中折抵，写回一致版本",
        )
    if fee is not None and clause_amount is not None and fee != clause_amount:
        return _row(
            field,
            claim,
            clause,
            "冲突",
            f"物业费金额不一致（房源 {format_amount(fee)} 元/月 vs "
            f"合同 {format_amount(clause_amount)} 元/月）：要求写回一致金额并注明缴纳周期",
        )
    return _row(
        field, claim, clause, "一致", f"与约定一致，按约履行（合同物业费由{clause_bearer or '未写明方'}承担）"
    )


def _pet_forbidden(text: str) -> bool | None:
    if not re.search(r"宠物|饲养|养宠", text):
        return None
    if _FORBID_RE.search(text):
        return True
    if _ALLOW_RE.search(text):
        return False
    return None


def _cmp_pet(h: dict[str, Any], clauses: list[dict[str, Any]]) -> VRow:
    field = "宠物"
    claim_text = "" if h["pet"] is None else str(h["pet"]).strip()
    clause = _find(clauses, keywords=("宠物", "饲养", "养宠"))
    claim = claim_text or "宠物（房源侧未填写）"
    if not claim_text:
        return _row(field, claim, clause, "无法判断", "先确认是否养宠、品种与数量，再核验合同宠物条款")
    if clause is None:
        return _row(
            field,
            claim,
            None,
            "未约定",
            "合同未约定宠物事项：要求在补充协议中写明允许饲养的品种与数量、退租恢复与损坏责任，避免只留口头承诺",
        )
    clause_forbidden = _pet_forbidden(_blob(clause))
    house_forbidden = (
        True if _FORBID_RE.search(claim_text) else (False if _ALLOW_RE.search(claim_text) else None)
    )
    if clause_forbidden is None or house_forbidden is None:
        return _row(
            field,
            claim,
            clause,
            "无法判断",
            "合同宠物条款表述不明确，请人工核对原文并要求写明“允许/禁止饲养”",
        )
    if house_forbidden != clause_forbidden:
        no = clause["no"] or "?"
        return _row(
            field,
            claim,
            clause,
            "冲突",
            f"房源承诺「{claim_text}」与合同第 {no} 条不一致：要求删除禁止饲养条款，"
            "改为“乙方可饲养已免疫宠物（品种与数量写明），退租时恢复原状”，并写明违约后果",
        )
    return _row(field, claim, clause, "一致", "与约定一致，按约履行；宠物损坏责任与退租恢复标准仍需书面确认")


def _cmp_available(h: dict[str, Any], clauses: list[dict[str, Any]]) -> VRow:
    field = "可入住时间"
    claim_text = "" if h["available"] is None else str(h["available"]).strip()
    clause = _find(clauses, keywords=("起租", "租赁期限", "租赁期", "交付", "入住"))
    claim = f"可入住时间：{claim_text}" if claim_text else "可入住时间（房源侧未填写）"
    if not claim_text:
        return _row(field, claim, clause, "无法判断", "先与房东确认可入住日期，再核对合同起租日与空置期")
    if clause is None:
        return _row(
            field,
            claim,
            None,
            "未约定",
            "合同未约定起租日：要求在补充协议中写明确切起租日期（YYYY 年 M 月 D 日）",
        )
    clause_start = _date(clause["date_from"]) or _date(clause["text"])
    if clause_start is None:
        return _row(
            field,
            claim,
            clause,
            "无法判断",
            "合同起租日解析不出具体日期，请人工核对原文并要求写明“自 YYYY 年 M 月 D 日起租”",
        )
    house_date = _date(claim_text, default_year=clause_start.year)
    if house_date is None:
        return _row(
            field,
            claim,
            clause,
            "无法判断",
            f"「{claim_text}」不是明确日期，无法与合同起租日 {clause_start.isoformat()} 逐天比较："
            "要求写成具体日期后再核验",
        )
    if house_date == clause_start:
        return _row(field, claim, clause, "一致", "起租日与承诺入住时间一致，按约履行")
    gap = abs((clause_start - house_date).days)
    if clause_start > house_date:
        return _row(
            field,
            claim,
            clause,
            "冲突",
            f"合同起租日（{clause_start.isoformat()}）晚于承诺入住时间（{house_date.isoformat()}），"
            f"空置 {gap} 天仍要计租：要求按实际入住日起租或减免空置期租金",
        )
    return _row(
        field,
        claim,
        clause,
        "冲突",
        f"合同起租日（{clause_start.isoformat()}）早于承诺入住时间（{house_date.isoformat()}），"
        f"产生 {gap} 天空置期租金：要求按实际入住日起租或减免空置期租金",
    )


def _cmp_area(h: dict[str, Any], clauses: list[dict[str, Any]]) -> VRow:
    field = "面积"
    area = h["area"]
    clause = _find(clauses, keywords=("建筑面积", "面积", "平方米", "㎡"))
    claim = f"建筑面积 {area} ㎡" if area is not None else "面积（房源侧未填写）"
    if area is None:
        return _row(field, claim, clause, "无法判断", "房源侧未记录面积，先确认建筑面积再与合同面积条款比较")
    if clause is None:
        return _row(
            field, claim, None, "未约定", "合同未写明面积：要求在补充协议中写明建筑面积，并以产权证明为准"
        )
    match = _AREA_RE.search(clause["text"])
    clause_area = float(match.group(1)) if match else None
    if clause_area is None:
        return _row(
            field,
            claim,
            clause,
            "无法判断",
            "合同面积条款解析不出数值，请人工核对原文并要求写明“建筑面积 X 平方米”",
        )
    if clause_area == float(area):
        return _row(field, claim, clause, "一致", "与合同一致，按约履行")
    return _row(
        field,
        claim,
        clause,
        "冲突",
        f"面积不一致（房源 {area} ㎡ vs 合同 {clause_area:g} ㎡）：要求以产权证明或实测面积为准写回一致面积，"
        "或按实测面积调整租金",
    )


def _cmp_agency(h: dict[str, Any], clauses: list[dict[str, Any]]) -> VRow:
    field = "中介费"
    fee = h["agencyFee"]
    rent = h["rent"]
    clause = _find(clauses, keywords=("中介费", "居间", "服务费"))
    if fee == 0:
        claim = "无中介费"
    elif fee is not None:
        claim = f"中介费 {format_amount(fee)} 元"
    else:
        claim = "中介费（房源侧未填写）"
    if clause is None:
        if fee is None:
            return _row(
                field, claim, None, "无法判断", "房源侧与合同均未说明中介费：签约前确认是否收取、金额与收款方"
            )
        return _row(
            field,
            claim,
            None,
            "未约定",
            "合同未约定中介费：要求在补充协议中写明中介费金额、承担方与支付节点后再付定金",
        )
    if fee is None:
        return _row(
            field, claim, clause, "无法判断", "合同有中介费条款但房源侧未记录金额，请人工核对合同金额"
        )
    clause_amount = clause["amount"] if clause["amount"] is not None else _money(clause["text"])
    if clause_amount is None and rent is not None:
        if "半个月" in clause["text"]:
            clause_amount = rent * 0.5
        elif "一个月租金" in clause["text"]:
            clause_amount = rent
    if clause_amount is None:
        return _row(
            field, claim, clause, "无法判断", "合同中介费条款解析不出金额，请人工核对原文并要求写明具体金额"
        )
    if clause_amount == fee:
        return _row(field, claim, clause, "一致", "金额一致，按约履行；保留付款凭证与发票")
    return _row(
        field,
        claim,
        clause,
        "冲突",
        f"中介费不一致（房源 {format_amount(fee)} 元 vs 合同 {format_amount(clause_amount)} 元）："
        "要求写回一致金额并确认收款方与发票，未写回前不付定金",
    )


def _cmp_utilities(h: dict[str, Any], clauses: list[dict[str, Any]]) -> VRow:
    field = "网费/水电燃气"
    net_fee, other_fee = h["netFee"], h["otherFee"]
    clause = _find(clauses, keywords=("网费", "宽带", "水费", "电费", "水电", "燃气", "公摊", "取暖", "供暖"))
    parts: list[str] = []
    if net_fee is not None:
        parts.append(f"网费 {format_amount(net_fee)} 元/月")
    if other_fee is not None and other_fee != "":
        parts.append(f"其他费用 {other_fee}")
    claim = "；".join(parts) if parts else "网费/水电燃气（房源侧未填写）"
    if not parts:
        return _row(
            field,
            claim,
            clause,
            "无法判断",
            "房源侧未记录网费/水电燃气等费用：签约前确认单价、计费方式与承担方",
        )
    if clause is None:
        return _row(
            field,
            claim,
            None,
            "未约定",
            "合同未约定网费/水电燃气等费用：要求在补充协议中写明单价、抄表方式与承担方",
        )
    clause_amount = clause["amount"] if clause["amount"] is not None else _money(clause["text"])
    house_total = _as_number(net_fee)
    if other_fee is not None and other_fee != "":
        other_value = _as_number(other_fee)
        house_total = None if other_value is None else (house_total or 0) + other_value
    if clause_amount is None:
        return _row(
            field,
            claim,
            clause,
            "无法判断",
            "合同费用条款解析不出金额，请人工核对原文并要求写明单价与计量方式",
        )
    if house_total is None:
        return _row(
            field, claim, clause, "无法判断", "房源侧费用合计无法折算为金额，请人工核对后与合同逐项比较"
        )
    if clause_amount == house_total:
        return _row(
            field,
            claim,
            clause,
            "一致",
            f"费用合计与合同一致（{format_amount(house_total)} 元/月），按约履行",
        )
    return _row(
        field,
        claim,
        clause,
        "冲突",
        f"费用不一致（房源合计 {format_amount(house_total)} 元/月 vs "
        f"合同 {format_amount(clause_amount)} 元/月）：要求写回一致金额与计量方式，避免入住后追加收费",
    )


def _cmp_lease(h: dict[str, Any], clauses: list[dict[str, Any]]) -> VRow:
    field = "租期"
    claim_text = "" if h["leaseReq"] is None else str(h["leaseReq"]).strip()
    clause = _find(clauses, types=("租期",), keywords=("租赁期限", "租赁期", "租期"))
    claim = f"租期要求：{claim_text}" if claim_text else "租期要求（房源侧未填写）"
    if not claim_text:
        return _row(field, claim, clause, "无法判断", "先确认租期要求（如一年 / 6 个月），再核对合同租赁期限")
    claim_months = _months(claim_text)
    if claim_months is None:
        return _row(
            field, claim, clause, "无法判断", f"「{claim_text}」解析不出租期月数，请写成“X 个月”后再核验"
        )
    if clause is None:
        return _row(field, claim, None, "未约定", "合同未约定租期：要求在补充协议中写明起止日期与总月数")
    clause_months = _months(clause["text"]) or clause["months"]
    if clause_months is None and clause["date_from"] and clause["date_to"]:
        start, end = _date(clause["date_from"]), _date(clause["date_to"])
        if start and end:
            clause_months = (end.year - start.year) * 12 + end.month - start.month
    if clause_months is None:
        return _row(field, claim, clause, "无法判断", "合同租赁期限解析不出月数，请人工核对起止日期")
    if clause_months == claim_months:
        return _row(field, claim, clause, "一致", "租期一致，按约履行；提前退租条件与违约金另行确认")
    return _row(
        field,
        claim,
        clause,
        "冲突",
        f"租期不一致（房源要求 {claim_months} 个月，合同为 {clause_months} 个月）："
        f"要求按 {claim_months} 个月修改起止日期；如需提前退租，写明退租条件与违约金，写回一致版本",
    )


def _cmp_sublet(h: dict[str, Any], clauses: list[dict[str, Any]]) -> VRow:
    field = "转租"
    claim_text = "" if h["sublet"] is None else str(h["sublet"]).strip()
    clause = _find(clauses, keywords=("转租", "分租", "转借"))
    claim = f"转租要求：{claim_text}" if claim_text else "转租要求（房源侧未填写）"
    if not claim_text:
        return _row(field, claim, clause, "无法判断", "先确认是否需要转租权，再核验合同转租条款")
    if clause is None:
        return _row(
            field,
            claim,
            None,
            "未约定",
            "合同未约定转租：要求在补充协议中写明“转租需甲方书面同意”及押金与租金责任",
        )
    house_allows = _SUBLET_ALLOW_RE.search(claim_text) is not None and _FORBID_RE.search(claim_text) is None
    clause_forbids = _FORBID_RE.search(clause["text"]) is not None and "转租" in clause["text"]
    consent_only = "书面同意" in clause["text"] and not clause_forbids
    if house_allows:
        if clause_forbids:
            no = clause["no"] or "?"
            return _row(
                field,
                claim,
                clause,
                "冲突",
                f"房源要求「{claim_text}」但合同第 {no} 条禁止转租：要求改为"
                "“经甲方书面同意可转租”，并写明转租期间的租金与押金责任",
            )
        return _row(
            field,
            claim,
            clause,
            "一致",
            "合同允许转租，按约履行" + ("；转租需甲方书面同意，保留书面同意记录" if consent_only else ""),
        )
    return _row(field, claim, clause, "一致", "与现状一致；后续如需转租需另行书面协商")


def _cmp_shared(h: dict[str, Any], clauses: list[dict[str, Any]]) -> VRow:
    field = "合租/入住人数"
    max_people = h["maxPeople"]
    clause = _find(clauses, keywords=("合租", "居住人数", "入住人数", "同住", "居住人"))
    parts: list[str] = []
    if h["shared"] is not None:
        parts.append("合租" if h["shared"] else "整租（不合租）")
    if max_people is not None:
        parts.append(f"入住人数上限 {_int(max_people)} 人")
    claim = "；".join(parts) if parts else "合租与入住人数（房源侧未填写）"
    if not parts:
        return _row(
            field, claim, clause, "无法判断", "房源侧未记录合租状态与入住人数：先确认再核验合同居住人数条款"
        )
    if clause is None:
        return _row(
            field,
            claim,
            None,
            "未约定",
            "合同未写明合租与入住人数：要求在补充协议中写明实际居住人、室友更换规则与人数上限",
        )
    text = _blob(clause)
    clause_forbids_shared = (
        "合租" in text and _FORBID_RE.search(text) is not None or "仅限承租人" in text or "仅供乙方" in text
    )
    match = _PEOPLE_RE.search(text)
    clause_limit = _cn_int(match.group(1)) if match else None
    if h["shared"] and clause_forbids_shared:
        return _row(
            field,
            claim,
            clause,
            "冲突",
            "房源为合租房源但合同禁止合租：要求改为“合租需甲方书面同意”，并写明室友更换与公区费用分摊规则",
        )
    if max_people is not None and clause_limit is not None and _int(max_people) > clause_limit:
        return _row(
            field,
            claim,
            clause,
            "冲突",
            f"入住人数上限不一致（房源 {_int(max_people)} 人 vs 合同 {clause_limit} 人）："
            f"要求按 {_int(max_people)} 人写回一致版本，或接受合同上限并同步修改房源记录",
        )
    if clause_limit is not None or clause_forbids_shared:
        return _row(field, claim, clause, "一致", "与约定一致，按约履行；入住人数变化需书面确认")
    return _row(
        field, claim, clause, "无法判断", "合同居住人数条款表述不明确，请人工核对原文并要求写明人数上限"
    )


_COMPARATORS = (
    _cmp_rent,
    _cmp_deposit,
    _cmp_property,
    _cmp_pet,
    _cmp_available,
    _cmp_area,
    _cmp_agency,
    _cmp_utilities,
    _cmp_lease,
    _cmp_sublet,
    _cmp_shared,
)


def compare_claims(
    house: Mapping[str, Any] | object, clauses: Sequence[Mapping[str, Any] | Sequence[Any] | object]
) -> list[VRow]:
    """房源承诺 × 合同条款逐项核验：固定 11 项，冲突在前（契约 §4.7 / PRD §3.3）。

    未匹配到条款一律 `未约定`（禁止推断为已承诺）；房源缺值或条款不可解析一律 `无法判断`。
    """
    h = normalise_house(house)
    clauses_norm = _clauses(clauses)
    rows = [comparator(h, clauses_norm) for comparator in _COMPARATORS]
    rows.sort(key=lambda row: RESULT_ORDER[row.result])  # 稳定排序：同类保持比较器定义顺序
    return rows
