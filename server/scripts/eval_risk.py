"""风险识别评测跑分。必须在 server 目录下运行（config 从 ./env 读取 key）：
    cd server && .venv/bin/python scripts/eval_risk.py --provider mock|llm
"""

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
REPO = SERVER.parent
sys.path.insert(0, str(SERVER / "src"))

from rentgraph.config import settings  # noqa: E402
from rentgraph.services.extract import finalize, grounding_ok, llm_extract, mock_extract  # noqa: E402
from rentgraph.services.rules import RULES  # noqa: E402

GT = json.loads((REPO / "evals" / "ground_truth.json").read_text(encoding="utf-8"))


def predict(clauses) -> set[tuple[int | None, str]]:
    out: set[tuple[int | None, str]] = set()
    for c in clauses:
        for rule in RULES:
            hit = rule(c)
            if hit:
                out.add((c.clause_no, hit.rule_id))
    return out


async def run_one(text: str, provider: str):
    t0 = time.time()
    if provider == "llm":
        raw = await llm_extract(text)
        clauses = finalize(grounding_ok(raw, text))
    else:
        clauses = finalize(mock_extract(text))
    return clauses, time.time() - t0


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["mock", "llm"], required=True)
    args = ap.parse_args()
    if args.provider == "llm":
        settings.llm_provider = "openai"
        if not getattr(settings, "llm" + "_api" + "_key"):
            sys.exit("未读到 LLM_API_KEY：请在 server/.env 配置后，于 server 目录下运行本脚本")
    items = GT["contracts"]
    sem = asyncio.Semaphore(4)

    tp = fp = fn = 0
    rule_stats: dict[str, Counter] = {}
    per_rule_expected: Counter = Counter()
    rows = []
    latencies = []

    async def process(item):
        text = (REPO / "evals" / item["file"]).read_text(encoding="utf-8")
        expected = {(e["clause_no"], e["rule_id"]) for e in item["expected"]}
        async with sem:
            clauses, lat = await run_one(text, args.provider)
        predicted = predict(clauses)
        return item["file"], expected, predicted, clauses, lat

    results = await asyncio.gather(*(process(i) for i in items))

    for name, expected, predicted, _clauses, lat in results:
        tp += len(expected & predicted)
        fp += len(predicted - expected)
        fn += len(expected - predicted)
        latencies.append(lat)
        for key in expected:
            per_rule_expected[key[1]] += 1
            st = rule_stats.setdefault(key[1], Counter())
            st["tp"] += int(key in predicted)
            st["fn"] += int(key not in predicted)
        for key in predicted - expected:
            st = rule_stats.setdefault(key[1], Counter())
            st["fp"] += 1
        rows.append(
            {
                "file": name,
                "expected": len(expected),
                "predicted": len(predicted),
                "missed": sorted(f"第{k[0]}条:{k[1]}" for k in expected - predicted),
                "false_alarms": sorted(f"第{k[0]}条:{k[1]}" for k in predicted - expected),
            }
        )

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    # 对外可宣称性：报告必须写清语料来源；合成集只能作回归冒烟，不能当真实能力数字
    corpus, labeling = GT.get("corpus", "unknown"), GT.get("labeling", "unknown")
    corpus_label = {
        "synthetic": "合成模板（`evals/generate.py`）+ 生成器自动打标 → 仅回归冒烟，不代表真实合同能力",
        "real": "真实脱敏合同 + 人工标注 → 可对外引用",
    }.get(corpus, f"corpus={corpus} / labeling={labeling} → 来源不明，不可对外引用")

    lines = [
        f"# 风险识别评测报告（extractor={args.provider} · {date.today()}）",
        "",
        f"- 语料来源：**{corpus_label}**",
        f"- 样本：{len(items)} 份合同（{GT.get('corpus_note') or '人工标注'}）",
        f"- 指标：precision **{precision:.1%}** / recall **{recall:.1%}** / F1 **{f1:.1%}**（TP={tp} FP={fp} FN={fn}）",
        f"- 平均抽取延迟：{sum(latencies) / len(latencies):.1f}s/份",
        "",
        "## 分规则明细",
        "",
        "| 规则 | 期望 | TP | FP | FN | 查全 | 查准 |",
        "|------|------|----|----|----|------|------|",
    ]
    for rid in sorted(per_rule_expected, key=lambda r: -per_rule_expected[r]):
        st = rule_stats.get(rid, Counter())
        exp = per_rule_expected[rid]
        rec = st["tp"] / exp if exp else 0
        pre = st["tp"] / (st["tp"] + st["fp"]) if st["tp"] + st["fp"] else 0
        lines.append(f"| {rid} | {exp} | {st['tp']} | {st['fp']} | {st['fn']} | {rec:.0%} | {pre:.0%} |")
    lines += ["", "## 逐份明细", "", "| 合同 | 期望 | 预测 | 漏报 | 误报 |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(
                f"| {r['file'].split('/')[-1]} | {r['expected']} | {r['predicted']} "
            f"| {'；'.join(r['missed']) or '—'} | {'；'.join(r['false_alarms']) or '—'} |"
        )

    if corpus != "real":
        lines += ["", "> 本报告数字只用于管线回归，不可对外宣称「真实合同风险识别能力」（见完善计划 §3）。"]

    out = REPO / "evals" / f"report-{args.provider}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"precision={precision:.1%} recall={recall:.1%} F1={f1:.1%} -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
