# RentGraph · 租房决策工作台

> 从选房到签约，帮你做出更可靠的租房决定。

一期范围与验收基线：[doc/prd/原型完善执行文档-v1.0.md](doc/prd/原型完善执行文档-v1.0.md)（v1.1）
技术栈与架构：[doc/arch/RentGraph-技术栈选型-2026.md](doc/arch/RentGraph-技术栈选型-2026.md)
接口契约（前后端事实源）：[doc/plan/后端-v1.1-接口契约.md](doc/plan/后端-v1.1-接口契约.md)

三条 P0 流程：**候选房源导入与字段确认 → 可解释推荐（三视图）→ 房源承诺 × 合同条款核验 → 上下文问答**。

## 组成

| 目录 | 内容 | 技术栈 |
|---|---|---|
| `web/` | 工作台前端（对话 + 候选房源 + 合同核验 + 抽屉） | React 19 · TypeScript · Vite 8 · Tailwind 4 · Zustand 5 · Font Awesome |
| `server/` | 后端 API（模块化单体） | FastAPI · Pydantic · SQLAlchemy async · LangChain 结构化输出 · SSE |
| `租房知识图谱-Agent-Frontend-Protype.html` | 已冻结的交互与视觉验收基线（像素级对照） | — |
| `doc/` | 产品 / 架构 / 计划 / 测试文档 | — |
| `evals/` | 合同核验评测语料与验收报告 | — |

## 快速开始

```bash
# 1. 后端（默认 SQLite + LLM_PROVIDER=mock，离线可跑）
cd server && ./\.venv/bin/python -m uvicorn rentgraph.main:app --port 8010
#    首次准备环境：uv venv .venv --python 3.11 && uv pip install -e ".[dev]"

# 2. 前端（dev 代理已把 /api、/healthz 转发到 8010）
cd web && pnpm install && pnpm dev        # http://localhost:5173
```

真实模型（可选，用于非离线解析/核验/问答）：

```bash
cd server && cp .env.example .env         # 填 LLM_PROVIDER=openai + LLM_BASE_URL/LLM_API_KEY/LLM_MODEL
```

前端两种模式：

- `VITE_API_MODE=api`（默认）：调用真实后端；
- `VITE_API_MODE=demo`：纯本地演示数据，用于与原型做像素回归。

## 验证

```bash
# 后端单元 + API 集成（130 个用例，离线确定性，约 7s）
cd server && ./.venv/bin/python -m pytest -q

# 端到端回放 PRD §10 三个场景（42 项检查）
cd server && ./.venv/bin/python scripts/acceptance_v11.py          # mock
cd server && ./.venv/bin/python scripts/acceptance_v11.py --llm    # 真实模型
# 报告：evals/report-v11.md（mock）/ evals/report-v11-llm.md（真实模型）

# 前端构建与类型检查
cd web && npx tsc --noEmit && pnpm build
```

## 一期边界（不可弱化）

- 数据属于**本次工作台临时上下文**（默认 72 小时过期），不承诺长期保存、不做房源库与库存指标。
- 不做平台抓取 / 房源真实性保证；不把「已验证」「真实有效」当成产品能力。
- 合同审查输出风险与建议，**不输出法律结论**；未在合同找到对应约定时结果必须是「未约定」。
- 图片与扫描件不做 OCR（明确为规划能力），PDF 需有文字层。
- 推荐的成本、预算/通勤过滤与三视图排序全部由确定性规则计算，LLM 只负责解释，且数字必须来自计算结果。

## 已知偏差

与选型文档的差异（SQLite 默认、进程内 RunManager 替代 ARQ+Redis、未接 LangGraph 状态图、未接 Orval 生成 client 等）逐条记录在
[doc/plan/后端-v1.1-接口契约.md](doc/plan/后端-v1.1-接口契约.md) §8，均为可替换实现并给出了升级路径。
