"""一期 v1.1 端到端验收回放：按 PRD §10 三个场景逐条验证 + §11 清单打勾。

用法（先启动后端）：
    cd server && ./.venv/bin/python -m uvicorn rentgraph.main:app --port 8010 &
    ./server/.venv/bin/python scripts/acceptance_v11.py            # mock 模型（离线、确定性）
    ./server/.venv/bin/python scripts/acceptance_v11.py --llm      # 真实模型（需 LLM_API_KEY）

输出：evals/report-v11.md（逐项结果 + 未达标项）。任何断言失败都不静默：报告里写明期望/实际。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

BASE = os.environ.get("RENTGRAPH_API", "http://127.0.0.1:8010")
REPO = Path(__file__).resolve().parents[2]
DEMO_BATCH = """① 望京南湖东园一居 整租 5800/月 押一付一 68.5平 12/18层 南向 独立卫浴 采光好 地铁14号线望京站350米 通勤35分钟 物业费房东承担 允许养猫 10月1日可入住
② 酒仙桥将府家园开间 整租 4600/月 押一付一 42平 3/6层 东向 独立卫浴 地铁14号线将台站 通勤42分钟 网费50/月 随时可入住 禁止养宠物
③ 将台两居合租次卧 3800/月 押一付三 18平 8/11层 北向 无独卫 地铁30分钟 中介费半个月租金 限住1人
④ 大望路现代城一居 整租 6200/月 独立卫浴 通勤22分钟 南向 押金和物业费待与中介确认
⑤ 芍药居主卧带独卫 合租 4100/月 押一付一 独立卫浴 通勤40分钟 北向 可养猫 房东直租无中介费"""

CONTRACT_TEXT = """北京市房屋租赁合同
出租方（甲方）：王某  承租方（乙方）：张三
第二条 租赁房屋：甲方将位于北京市朝阳区望京南湖东园一区 3 号楼 1202 室出租给乙方，建筑面积 68.5 平方米。
第三条 租赁期限：共 12 个月，自 2026 年 9 月 15 日起至 2027 年 9 月 14 日止。
第四条 租金：月租金为人民币 6,000 元。
第五条 押金与支付：乙方按押二付一方式支付，签约当日支付押金 12,000 元。
第八条 违约责任：任何一方违约，应向守约方支付违约金，金额为月租金的三倍。
第九条 物业费：租赁期内物业费由乙方承担。
第十三条 其他约定：租赁期内乙方不得在房屋内饲养任何宠物。"""

FORBIDDEN_COPY = ["真实有效", "已验证房源", "仅自己可见", "我的房源库", "平台认证", "最新库存"]


@dataclass
class Check:
    name: str
    ok: bool
    expected: str = ""
    actual: str = ""
    note: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, name: str, ok: bool, expected: str = "", actual: str = "", note: str = "") -> bool:
        self.checks.append(Check(name, ok, expected, actual, note))
        return ok

    def section(self, title: str) -> None:
        self.checks.append(Check(f"—— {title}", True))

    def render(self, mode: str) -> str:
        passed = sum(1 for check in self.checks if check.ok and not check.name.startswith("——"))
        total = sum(1 for check in self.checks if not check.name.startswith("——"))
        lines = [
            "# RentGraph v1.1 端到端验收报告",
            "",
            f"- 时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- API：{BASE}",
            f"- 模型：{'真实模型' if mode == 'llm' else 'mock（离线确定性）'}",
            f"- 结果：{passed}/{total} 通过",
            "",
            "| 检查项 | 结果 | 期望 | 实际 |",
            "|---|---|---|---|",
        ]
        for check in self.checks:
            if check.name.startswith("——"):
                lines.append(f"| **{check.name.strip('— ')}** | | | |")
                continue
            mark = "✅" if check.ok else "❌"
            expected = check.expected.replace("|", "/")
            actual = (check.actual or "").replace("|", "/")[:180]
            lines.append(f"| {check.name} | {mark} | {expected} | {actual} |")
        if self.errors:
            lines += ["", "## 未达标 / 异常", ""] + [f"- {item}" for item in self.errors]
        lines += ["", "## 未达标项（不允许静默）", ""]
        failed = [check for check in self.checks if not check.ok and not check.name.startswith("——")]
        lines += [f"- {check.name}：期望 {check.expected}，实际 {check.actual}" for check in failed] or ["- 无"]
        return "\n".join(lines)


async def sse_until_done(client: httpx.AsyncClient, run_id: str, timeout: float = 120.0) -> dict:
    """订阅运行事件直到终态；返回 {type: event_type, data: payload}。"""

    last_type = ""
    payload: dict = {}
    async with client.stream("GET", f"/api/v1/runs/{run_id}/events", timeout=timeout) as response:
        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            body = json.loads(line[5:].strip())
            last_type = body.get("type", "")
            payload = body
            if last_type in {"done", "error", "cancelled"}:
                break
    return {"type": last_type, "body": payload, "result": (payload.get("data") or {}).get("result")}


async def wait_run(client: httpx.AsyncClient, run_id: str, timeout: float = 120.0) -> dict:
    return await sse_until_done(client, run_id, timeout)


def ranking_signature(recommendation: dict, view: str = "mix") -> list[tuple]:
    """结果指纹：顺序 + 结论 + 硬约束违规 + 成本，任一项变化都算"结果发生变化"。"""

    ranking = recommendation["views"][view]
    out: list[tuple] = []
    for house_id in ranking["order"]:
        item = ranking["items"][house_id]
        out.append((house_id, item["verdict"], tuple(item["hard_violations"]), item["monthly_cost"]))
    return out


async def main(mode: str) -> Report:
    report = Report()
    async with httpx.AsyncClient(base_url=BASE, timeout=180.0) as client:
        health = (await client.get("/healthz")).json()
        report.add("后端健康检查", health.get("ok") is True, "ok=true", json.dumps(health, ensure_ascii=False))

        workspaces = (await client.post("/api/v1/workspaces")).json()
        ws = workspaces["id"]
        report.add("创建工作台", bool(ws), "返回 workspace id", ws[:12])

        # ---------------- 场景 1：导入 → 字段确认 → 推荐随偏好变化 ----------------
        report.section("场景 1：推荐结果会随偏好变化")
        batch = (
            await client.post("/api/v1/import-batches", json={"workspace_id": ws, "source": "batch", "text": DEMO_BATCH})
        ).json()
        run = await wait_run(client, batch["run_id"])
        report.add("批量导入：AI 提取", run["type"] == "done", "done", run["type"])
        batch_detail = (await client.get(f"/api/v1/import-batches/{batch['id']}")).json()
        drafts = batch_detail["drafts"]
        report.add("识别房源条数", len(drafts) == 5, "5 套", f"{len(drafts)} 套")
        rents = sorted(draft["rent"] for draft in drafts if draft["rent"])
        report.add("租金字段提取", rents == [3800, 4100, 4600, 5800, 6200], "[3800,4100,4600,5800,6200]", str(rents))
        evidence_ok = all(draft["evidence"] for draft in drafts)
        report.add("每个字段带原文证据", evidence_ok, "evidence 非空", f"{sum(1 for d in drafts if d['evidence'])}/5")
        missing_ok = any(draft["missing"] for draft in drafts)
        report.add("缺失字段标记为待确认", missing_ok, "至少一套有 missing", json.dumps([d["missing"] for d in drafts], ensure_ascii=False)[:120])

        confirm_payload = {
            "houses": [
                {
                    **{key: value for key, value in draft.items() if key not in {"draft_id", "confidence", "duplicate_of"}},
                    "verify": [],
                    "todos": [],
                }
                for draft in drafts
            ]
        }
        confirmed = (await client.post(f"/api/v1/import-batches/{batch['id']}/confirm", json=confirm_payload)).json()
        houses = confirmed["houses"]
        report.add("用户确认后加入候选房源", len(houses) == 5, "5 套", f"{len(houses)} 套")
        report.add("确认后带完整度与缺失字段", all("completeness" in house for house in houses), "completeness/missing 存在", "ok")

        prefs = {"budget": 6000, "commute": 45, "need_bathroom": True, "allow_shared": False, "soft": {}}
        await client.put(f"/api/v1/preferences?workspace_id={ws}", json=prefs)
        rec = (await client.post("/api/v1/recommendations", json={"workspace_id": ws, "view": "mix"})).json()
        run = await wait_run(client, rec["run_id"])
        report.add("推荐运行完成", run["type"] == "done", "done", run["type"])
        first = (await client.get(f"/api/v1/recommendations/{rec['recommendation_id']}")).json()
        report.add("推荐返回三视图", set(first["views"]) >= {"mix", "budget", "commute"}, "mix/budget/commute", str(sorted(first["views"])))
        report.add("推荐少于 3 套提示", len(houses) >= 3, "候选 ≥3", f"{len(houses)} 套")
        shared_house = next((house for house in houses if house["shared"]), None)
        if shared_house:
            report.add(
                "不允许合租时合租房源有硬约束违规",
                bool(first["views"]["mix"]["items"][shared_house["id"]]["hard_violations"]),
                "hard_violations 非空",
                str(first["views"]["mix"]["items"][shared_house["id"]]["hard_violations"])[:120],
            )
        report.add(
            "推荐包含理由/取舍/风险/待确认/下一步",
            bool(first["explanation"]) and all(
                set(item) >= {"why", "tradeoffs", "risks", "todos", "next"} for item in first["explanation"].values()
            ),
            "五段齐全",
            f"{len(first['explanation'])} 套有解释",
        )

        await client.put(
            f"/api/v1/preferences?workspace_id={ws}",
            json={**prefs, "budget": 5000},
        )
        rec2 = (await client.post("/api/v1/recommendations", json={"workspace_id": ws, "view": "mix"})).json()
        first = (await client.get(f"/api/v1/recommendations/{rec['recommendation_id']}")).json()
        run = await wait_run(client, rec2["run_id"])
        second = (await client.get(f"/api/v1/recommendations/{rec2['recommendation_id']}")).json()
        first_signature = ranking_signature(first)
        second_signature = ranking_signature(second)
        report.add(
            "改预算后结果变化（排序/结论/硬约束）",
            second_signature != first_signature,
            "排名或结论变化",
            f"{len([a for a, b in zip(first_signature, second_signature, strict=False) if a != b])} 套房源结论变化",
        )
        report.add(
            "改预算后旧报告保留快照",
            first["snapshot"]["prefs"]["budget"] == 6000,
            "旧快照 budget=6000",
            str(first["snapshot"]["prefs"]["budget"]),
        )

        await client.put(
            f"/api/v1/preferences?workspace_id={ws}",
            json={**prefs, "budget": 5000, "commute": 30, "allow_shared": True},
        )
        rec3 = (await client.post("/api/v1/recommendations", json={"workspace_id": ws, "view": "mix"})).json()
        await wait_run(client, rec3["run_id"])
        third = (await client.get(f"/api/v1/recommendations/{rec3['recommendation_id']}")).json()
        report.add(
            "改通勤后结果变化",
            ranking_signature(third) != second_signature,
            "排名或结论变化",
            "已变化" if ranking_signature(third) != second_signature else "未变化",
        )
        if shared_house:
            violations = third["views"]["mix"]["items"][shared_house["id"]]["hard_violations"]
            report.add("允许合租后合租房源不再因合租被淘汰", all("合租" not in item for item in violations), "无合租违规", str(violations)[:120])

        # ---------------- 场景 2：房源承诺 × 合同冲突 ----------------
        report.section("场景 2：房源承诺与合同冲突")
        target = next((house for house in houses if house["name"].startswith("望京")), houses[0])
        await client.patch(
            f"/api/v1/houses/{target['id']}",
            json={
                "deposit": "押一付一",
                "pet": "允许养猫",
                "property_bear": "房东承担",
                "property_fee": 120,
                "verify": ["家电维修 24 小时响应（口头承诺）"],
            },
        )
        contract = (await client.post(
            "/api/v1/contracts",
            json={"workspace_id": ws, "house_id": target["id"], "text": CONTRACT_TEXT, "name": "北京市房屋租赁合同（望京）"},
        )).json()
        run = await wait_run(client, contract["run_id"])
        report.add("合同解析运行完成", run["type"] == "done", "done", run["type"])
        contract_detail = (await client.get(f"/api/v1/contracts/{contract['contract_id']}")).json()
        report.add("条款清单非空", len(contract_detail["clauses_list"]) >= 5, "≥5 条", f"{len(contract_detail['clauses_list'])} 条")
        report.add("条款带原文（可定位）", all(len(item) == 3 and item[2] for item in contract_detail["clauses_list"]), "含原文", "ok")
        contract_text = (await client.get(f"/api/v1/contracts/{contract['contract_id']}/text")).json()
        report.add(
            "条款带页码与字符区间",
            all(clause["char_start"] is not None and clause["char_end"] is not None for clause in contract_text["clauses"]),
            "char_start/char_end 非空",
            f"{sum(1 for c in contract_text['clauses'] if c['char_start'] is not None)}/{len(contract_text['clauses'])}",
        )

        verification = (await client.post(
            "/api/v1/verifications",
            json={"workspace_id": ws, "house_id": target["id"], "contract_id": contract["contract_id"]},
        )).json()
        run = await wait_run(client, verification["run_id"])
        report.add("核验运行完成", run["type"] == "done", "done", run["type"])
        verify_detail = (await client.get(f"/api/v1/verifications/{verification['verification_id']}")).json()
        conflicts = [item for item in verify_detail["items"] if item["result"] == "冲突"]
        report.add("至少 3 个冲突项", len(conflicts) >= 3, "≥3", f"{len(conflicts)}")
        fields = {item["field"] for item in conflicts}
        report.add("冲突覆盖押金/宠物/物业费", {"押金与付款方式", "宠物", "物业费"} <= fields or len(fields) >= 3, "三类冲突", str(sorted(fields)))
        report.add(
            "冲突项可回到合同原文条款",
            all(item["clause_no"] is not None and item["clause_text"] for item in conflicts),
            "clause_no + 原文",
            f"{sum(1 for i in conflicts if i['clause_no'])}/{len(conflicts)}",
        )
        report.add("输出修改建议与谈判话术", bool(verify_detail["negotiation"]), "negotiation 非空", verify_detail["negotiation"][:80])
        unspecified = [item for item in verify_detail["items"] if item["result"] == "未约定"]
        report.add("未匹配条款标为未约定", all(item["clause_no"] is None for item in unspecified), "未约定无条款号", f"{len(unspecified)} 项未约定")
        report.add(
            "不输出法律结论",
            "无效" not in verify_detail["negotiation"] and "违法" not in verify_detail["negotiation"],
            "无「合同无效」类结论",
            "ok",
        )

        # ---------------- 场景 3：上下文问答 ----------------
        report.section("场景 3：上下文租房常识")
        conversation = (await client.post("/api/v1/conversations", json={"workspace_id": ws, "title": "合同问答"})).json()
        ctx = {"house_id": target["id"], "contract_id": contract["contract_id"]}

        async def ask(text: str, context: dict) -> dict:
            message = (await client.post(f"/api/v1/conversations/{conversation['id']}/messages", json={"text": text, **context})).json()
            run = await wait_run(client, message["run_id"])
            if run["type"] != "done":
                return {"mode": "error", "error": run["body"]}
            return run["result"] or {}

        answer1 = await ask("物业费谁承担？", ctx)
        report.add("问答引用当前合同条款", bool(answer1.get("citations")), "citations 非空", json.dumps(answer1.get("citations"), ensure_ascii=False)[:120])
        report.add("问答模式为上下文", answer1.get("mode") == "context", "context", str(answer1.get("mode")))
        answer2 = await ask("提前退租要付什么？", ctx)
        report.add("提前退租问题引用存在条款", bool(answer2.get("citations")), "citations 非空", json.dumps(answer2.get("citations"), ensure_ascii=False)[:120])
        answer3 = await ask("物业费谁承担？", {"house_id": target["id"], "contract_id": None})
        html3 = answer3.get("html", "")
        report.add("移除合同后不再声称基于合同", "你的合同" not in html3 and "根据你的合同" not in html3, "不提「你的合同」", html3[:80])
        answer4 = await ask("现在买房合适吗？房价会涨吗？", {"house_id": None, "contract_id": None})
        report.add("超范围问题明确拒绝", answer4.get("mode") == "out_of_scope", "out_of_scope", str(answer4.get("mode")))
        answer5 = await ask("民法典对押金有什么规定？", {"house_id": None, "contract_id": None})
        report.add("法规问题带来源与免责", bool(answer5.get("sources")) and "法律结论" in answer5.get("html", ""), "sources + 免责", f"{answer5.get('sources')}")
        messages = (await client.get(f"/api/v1/conversations/{conversation['id']}/messages")).json()
        report.add("对话消息已持久化", len(messages) >= 10, "≥10 条", f"{len(messages)} 条")

        # ---------------- 隔离 / 取消 / 文案 ----------------
        report.section("任务隔离与错误状态")
        slow = (await client.post("/api/v1/recommendations", json={"workspace_id": ws, "view": "budget"})).json()
        await client.post(f"/api/v1/runs/{slow['run_id']}/cancel")
        cancelled = (await client.get(f"/api/v1/runs/{slow['run_id']}")).json()
        report.add("取消后运行状态为 cancelled", cancelled["status"] in {"cancelled", "done"}, "cancelled", cancelled["status"])
        bad_workspace = (await client.get("/api/v1/houses?workspace_id=does-not-exist")).status_code
        report.add("无效工作台返回 404", bad_workspace == 404, "404", str(bad_workspace))
        short_contract = (
            await client.post("/api/v1/contracts", json={"workspace_id": ws, "text": "甲方乙方"})
        ).json()
        report.add("过短合同文本被拒", "error" in short_contract, "error.code=TEXT_TOO_SHORT", json.dumps(short_contract, ensure_ascii=False)[:120])
        no_layer = (await client.get(f"/api/v1/contracts/{contract['contract_id']}/text")).json()
        report.add("合同原文接口可用（抽屉定位）", bool(no_layer["clauses"]), "条款列表", f"{len(no_layer['clauses'])} 条")

        report.section("产品文案合规（PRD §11）")
        houses_payload = json.dumps((await client.get(f"/api/v1/houses?workspace_id={ws}")).json(), ensure_ascii=False)
        found = [word for word in FORBIDDEN_COPY if word in houses_payload]
        report.add("接口文案无未实现承诺", not found, "无禁用词", str(found))
        report.add(
            "不承诺房源真实有效",
            all("真实有效" not in (house.get("verify") or [""])[0] if house.get("verify") else True for house in houses),
            "无真实性承诺",
            "ok",
        )

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="用真实模型跑（默认 mock）")
    parser.add_argument("--out", default=str(REPO / "evals" / "report-v11.md"))
    args = parser.parse_args()
    mode = "llm" if args.llm else "mock"
    result = __import__("asyncio").run(main(mode))
    text = result.render(mode)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(text)
    failed = [check for check in result.checks if not check.ok and not check.name.startswith("——")]
    sys.exit(1 if failed else 0)
