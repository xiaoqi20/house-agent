"""评测集生成器：从条款变体池组卷 20 份合成合同，ground truth 随生成自动标注。

用法: python3 evals/generate.py   （在仓库任意位置运行均可，路径自定位）
产出: evals/contracts/contract_NN.txt + evals/ground_truth.json

变体标签 = (expected_rule_ids)：每个变体自带“应命中规则”，组卷后按实际条号转成 (clause_no, rule_id)。
"""

import json
from pathlib import Path

HERE = Path(__file__).parent

# ---------- 条款变体池：(编号无关的文本, 该变体应触发的 rule_id 列表) ----------
RISKY_DEPOSIT = (
    "押金 乙方于签约当日支付房屋租赁押金人民币 {dep} 元。租赁期满，房屋及设施无损坏的，甲方退还押金。",
    ["deposit-no-deadline", "deposit-vague-damage", "no-handover"],
)
SAFE_DEPOSIT = (
    "押金 乙方于签约当日支付房屋租赁押金人民币 {dep} 元。租赁期满或合同解除且双方签署《房屋交接单》后 3 个工作日内，"
    "甲方全额无息退还押金；如需扣除费用，按市场价折旧并提供维修凭证。",
    [],
)
PENALTY_3X = (
    "违约责任 任何一方违约的，应向守约方支付违约金，违约金金额为月租金的三倍，并赔偿由此造成的全部损失。",
    ["over-penalty"],
)
PENALTY_2M = (
    "违约责任 乙方提前退租的，应向甲方支付违约金，违约金标准为相当于两个月租金的数额。",
    ["over-penalty"],
)
PENALTY_FAIR = (
    "违约责任 任何一方违约的，应向守约方支付违约金，违约金为一个月的租金标准，不多不少。",
    [],
)
RENT_UNCLEAR_FEES = ("租金 月租金为人民币 {rent} 元，按押一付三方式支付，乙方应于每期开始前 7 日支付。", ["unclear-fees"])
RENT_WITH_FEES = (
    "租金 月租金为人民币 {rent} 元，按押一付三方式支付；物业费、水电费、供暖费、网络费均由甲方承担。",
    [],
)
RENT_PREPAY_HEAVY = (
    "租金 月租金为人民币 {rent} 元，按押二付六方式支付；物业费、水电费由甲方承担，供暖费乙方承担。",
    ["long-prepay"],
)
REPAIR_BAD = ("房屋维修 租赁期内，因乙方使用不当造成的房屋及设施损坏，由乙方负责维修或赔偿。", ["repair-inverted"])
REPAIR_FAIR = (
    "房屋维修 因乙方使用不当造成的损坏由乙方负责；自然损耗及设施老化由甲方负责维修并承担费用。",
    [],
)
RENEW_TRAP = (
    "续租 租赁期届满前 30 日内乙方未书面通知甲方不续租的，视为自动续租一年，续租期间租金在上一年度基础上上浮 5%。",
    ["auto-renewal"],
)
RENEW_FAIR = ("续租 租期届满需续租的，双方应提前 30 日另行协商并重新签订合同。", [])
TERMINATE_ONEWAY = (
    "合同解除 甲方有权提前三十日通知乙方解除合同并收回房屋；乙方不得中途退租，否则押金不退。",
    ["unilateral-termination"],
)
TERMINATE_FAIR = (
    "合同解除 甲方有权提前三十日书面通知解除合同；乙方有权提前三十日书面通知退租，双方权利义务对等。",
    [],
)
SUBLEASE_BAN = ("转租 未经甲方书面同意，乙方不得转租、分租或转借房屋，违者视为根本违约。", ["sublease-ban"])
SUBLEASE_OK = ("转租 经甲方书面同意后，乙方可以将房屋全部或部分转租给第三人使用。", [])

HEAD = ("租赁房屋 甲方将位于{addr}房屋出租给乙方居住使用，建筑面积 {area} 平方米。", [])
TERM = ("租赁期限 租赁期共 {months} 个月，自 {d1} 起至 {d2} 止。", [])
USE = ("房屋用途 该房屋仅作为乙方居住使用，乙方不得改变房屋用途或用于经营活动。", [])
DELIVER = ("房屋交付 甲方应于起租日前将房屋按约定条件交付乙方，水、电、燃气底数以《房屋交割记录》为准。", [])
DISPUTE = ("争议解决 因履行本合同发生的争议，双方应协商解决；协商不成的，可向房屋所在地人民法院提起诉讼。", [])
NOTICE = ("通知送达 双方往来通知以本合同载明地址或微信号为准，拒收或地址变更未告知的视为送达。", [])


def pool(variant: str):
    return {
        "RISKY_DEPOSIT": RISKY_DEPOSIT,
        "SAFE_DEPOSIT": SAFE_DEPOSIT,
        "PENALTY_3X": PENALTY_3X,
        "PENALTY_2M": PENALTY_2M,
        "PENALTY_FAIR": PENALTY_FAIR,
        "RENT_UNCLEAR_FEES": RENT_UNCLEAR_FEES,
        "RENT_WITH_FEES": RENT_WITH_FEES,
        "RENT_PREPAY_HEAVY": RENT_PREPAY_HEAVY,
        "REPAIR_BAD": REPAIR_BAD,
        "REPAIR_FAIR": REPAIR_FAIR,
        "RENEW_TRAP": RENEW_TRAP,
        "RENEW_FAIR": RENEW_FAIR,
        "TERMINATE_ONEWAY": TERMINATE_ONEWAY,
        "TERMINATE_FAIR": TERMINATE_FAIR,
        "SUBLEASE_BAN": SUBLEASE_BAN,
        "SUBLEASE_OK": SUBLEASE_OK,
    }[variant]


# ---------- 20 份组卷计划（每行: 押金, 违约金, 租金, 维修, 续租, 解约, 转租, 是否含争议/送达条款） ----------
COMPOSITIONS = [
    ("RISKY_DEPOSIT", "PENALTY_3X", "RENT_UNCLEAR_FEES", "REPAIR_BAD", "RENEW_TRAP", "TERMINATE_ONEWAY", "SUBLEASE_BAN", True),
    ("RISKY_DEPOSIT", "PENALTY_FAIR", "RENT_WITH_FEES", "REPAIR_FAIR", "RENEW_FAIR", "TERMINATE_FAIR", "SUBLEASE_OK", False),
    ("SAFE_DEPOSIT", "PENALTY_2M", "RENT_PREPAY_HEAVY", "REPAIR_FAIR", "RENEW_TRAP", "TERMINATE_FAIR", "SUBLEASE_BAN", True),
    ("RISKY_DEPOSIT", "PENALTY_3X", "RENT_WITH_FEES", "REPAIR_FAIR", "RENEW_FAIR", "TERMINATE_ONEWAY", "SUBLEASE_OK", False),
    ("SAFE_DEPOSIT", "PENALTY_FAIR", "RENT_WITH_FEES", "REPAIR_BAD", "RENEW_FAIR", "TERMINATE_FAIR", "SUBLEASE_BAN", True),
    ("RISKY_DEPOSIT", "PENALTY_3X", "RENT_PREPAY_HEAVY", "REPAIR_FAIR", "RENEW_TRAP", "TERMINATE_FAIR", "SUBLEASE_BAN", False),
    ("SAFE_DEPOSIT", "PENALTY_2M", "RENT_UNCLEAR_FEES", "REPAIR_FAIR", "RENEW_FAIR", "TERMINATE_ONEWAY", "SUBLEASE_OK", True),
    ("RISKY_DEPOSIT", "PENALTY_FAIR", "RENT_WITH_FEES", "REPAIR_FAIR", "RENEW_FAIR", "TERMINATE_FAIR", "SUBLEASE_OK", False),
    ("RISKY_DEPOSIT", "PENALTY_3X", "RENT_WITH_FEES", "REPAIR_BAD", "RENEW_FAIR", "TERMINATE_FAIR", "SUBLEASE_BAN", True),
    ("SAFE_DEPOSIT", "PENALTY_2M", "RENT_WITH_FEES", "REPAIR_FAIR", "RENEW_TRAP", "TERMINATE_ONEWAY", "SUBLEASE_OK", False),
    ("RISKY_DEPOSIT", "PENALTY_FAIR", "RENT_UNCLEAR_FEES", "REPAIR_FAIR", "RENEW_FAIR", "TERMINATE_ONEWAY", "SUBLEASE_BAN", True),
    ("SAFE_DEPOSIT", "PENALTY_3X", "RENT_PREPAY_HEAVY", "REPAIR_BAD", "RENEW_FAIR", "TERMINATE_FAIR", "SUBLEASE_OK", False),
    ("RISKY_DEPOSIT", "PENALTY_3X", "RENT_WITH_FEES", "REPAIR_FAIR", "RENEW_TRAP", "TERMINATE_ONEWAY", "SUBLEASE_BAN", True),
    ("SAFE_DEPOSIT", "PENALTY_FAIR", "RENT_WITH_FEES", "REPAIR_FAIR", "RENEW_FAIR", "TERMINATE_FAIR", "SUBLEASE_OK", False),
    ("RISKY_DEPOSIT", "PENALTY_2M", "RENT_PREPAY_HEAVY", "REPAIR_FAIR", "RENEW_FAIR", "TERMINATE_ONEWAY", "SUBLEASE_BAN", True),
    ("SAFE_DEPOSIT", "PENALTY_3X", "RENT_UNCLEAR_FEES", "REPAIR_BAD", "RENEW_TRAP", "TERMINATE_FAIR", "SUBLEASE_OK", False),
    ("RISKY_DEPOSIT", "PENALTY_FAIR", "RENT_WITH_FEES", "REPAIR_FAIR", "RENEW_TRAP", "TERMINATE_ONEWAY", "SUBLEASE_BAN", True),
    ("SAFE_DEPOSIT", "PENALTY_2M", "RENT_WITH_FEES", "REPAIR_BAD", "RENEW_FAIR", "TERMINATE_ONEWAY", "SUBLEASE_OK", False),
    ("RISKY_DEPOSIT", "PENALTY_3X", "RENT_PREPAY_HEAVY", "REPAIR_FAIR", "RENEW_TRAP", "TERMINATE_ONEWAY", "SUBLEASE_BAN", True),
    ("SAFE_DEPOSIT", "PENALTY_FAIR", "RENT_UNCLEAR_FEES", "REPAIR_FAIR", "RENEW_FAIR", "TERMINATE_FAIR", "SUBLEASE_BAN", False),
]

CN = "一二三四五六七八九十"


def cn_no(i: int) -> str:
    if i <= 10:
        return CN[i - 1]
    return f"{CN[i // 10 - 1] if i // 10 > 1 else ''}十{CN[i % 10 - 1] if i % 10 else ''}".strip() or "十"


CITIES = [
    ("北京市朝阳区望京街道", "6500", "6500", "68.5", "2026年9月15日", "2027年9月14日", 12),
    ("北京市海淀区中关村南大街", "8200", "8200", "55.0", "2026年10月1日", "2027年9月30日", 12),
    ("上海市徐汇区田林路", "7400", "7400", "61.2", "2026年8月20日", "2027年8月19日", 12),
    ("杭州市西湖区文三路", "5600", "5600", "48.8", "2026年11月1日", "2027年10月31日", 12),
    ("成都市武侯区天府大道", "4200", "4200", "76.0", "2026年9月1日", "2028年8月31日", 24),
]


def build(idx: int):
    comp = COMPOSITIONS[idx]
    city = CITIES[idx % len(CITIES)]
    addr, rent, dep, area, d1, d2, months = city
    bodies = [
        (HEAD[0].format(addr=addr + f"某小区{idx + 3}号楼 120{idx % 9} 室", area=area), HEAD[1]),
        (USE[0], USE[1]),
        (TERM[0].format(months=months, d1=d1, d2=d2), TERM[1]),
        (pool(comp[2])[0].format(rent=rent), pool(comp[2])[1]),
        (DELIVER[0], DELIVER[1]),
        (pool(comp[0])[0].format(dep=dep), pool(comp[0])[1]),
        (pool(comp[1])[0], pool(comp[1])[1]),
    ]
    extras = [(pool(v)[0], pool(v)[1]) for v in comp[3:7]]
    if comp[7]:
        extras.append(DISPUTE)
    clauses = bodies + extras
    lines, expected = [], []
    for i, (body, rules) in enumerate(clauses, start=1):
        lines.append(f"第{cn_no(i)}条 {body}")
        for r in rules:
            expected.append({"clause_no": i, "rule_id": r})
    header = f"{'北京市' if idx % 5 == 0 else '城市'}房屋租赁合同（样本 {idx + 1:02d}）"
    text = header + "\n" + "\n".join(lines) + "\n"
    return text, expected


def main():
    out = HERE / "contracts"
    out.mkdir(exist_ok=True)
    gt = {"note": "模板化合成的真实语料替身；拿到真实脱敏合同后可直接替换 contracts/ 并同步 ground_truth.json", "contracts": []}
    for i in range(20):
        text, expected = build(i)
        name = f"contract_{i + 1:02d}.txt"
        (out / name).write_text(text, encoding="utf-8")
        gt["contracts"].append({"file": f"contracts/{name}", "expected": expected})
    (HERE / "ground_truth.json").write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(c["expected"]) for c in gt["contracts"])
    print(f"generated 20 contracts, {total} expected risk annotations")


if __name__ == "__main__":
    main()
