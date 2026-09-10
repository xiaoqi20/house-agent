# RentGraph 后端（server/）

一期产品承诺见 `doc/prd/原型完善执行文档-v1.0.md`；接口契约见 `doc/plan/后端-v1.1-接口契约.md`。

## 快速开始

```bash
cd server
cp .env.example .env                 # 默认 SQLite + LLM_PROVIDER=mock，无需任何外部服务
./.venv/bin/python -m uvicorn rentgraph.main:app --port 8010 --reload
curl -s localhost:8010/healthz       # {"ok":true,...}
```

启动后 `server/openapi.json` 会重新生成（前端 `pnpm gen:api` 用）。

## 模型

| 模式 | 说明 |
|---|---|
| `LLM_PROVIDER=mock`（默认） | 全部确定性规则（正则抽取 + 规则核验 + 模板话术），离线可跑，测试与像素回归都用它 |
| `LLM_PROVIDER=openai` | LangChain `ChatOpenAI` → 百炼 `qwen3.8-flash`（`LLM_BASE_URL`/`LLM_API_KEY`）；结构化输出走 Pydantic schema，抽取结果必须能在原文定位（`grounding_ok`），模型失败会返回错误事件而不是假报告 |

## 数据库

- 默认 `sqlite+aiosqlite:///./rentgraph.db`（一期演示/测试）。
- 生产按选型文档用 Postgres 18：`docker compose up -d db` 后设置 `DATABASE_URL`；模型层用 `JSON.with_variant(JSONB)`，两边通用。

## 测试

```bash
./.venv/bin/python -m pytest -q                     # 全量（离线，LLM_PROVIDER=mock）
./.venv/bin/python -m pytest tests/test_parsing.py -q
```

## 端到端验收（PRD §10 三场景）

```bash
./.venv/bin/python scripts/acceptance_v11.py        # mock，离线
./.venv/bin/python scripts/acceptance_v11.py --llm  # 真实模型（需 LLM_API_KEY）
# 报告写到 evals/report-v11.md
```

## 目录

```
src/rentgraph/
├── main.py             FastAPI 装配 + 异常映射 + OpenAPI 导出
├── config.py           配置（DB / 工作台有效期 / LLM）
├── models.py           ORM（工作台/批次/房源/偏好/推荐/合同/条款/核验/对话/运行）
├── errors.py           统一错误码 → HTTP 状态与用户提示
├── api/                路由：workspaces / import-batches / houses / preferences /
│                       recommendations / contracts / verifications / conversations / runs
└── services/
    ├── runs.py         RunManager：运行、事件日志、SSE 订阅、取消
    ├── engine.py       门面：解析 / 领域 / LLM 三层收敛为稳定接口
    ├── parsing.py      文件解析（txt/csv/md/xlsx/xls/docx/pdf；.doc 一期拒绝）
    ├── domain.py       确定性领域核心（成本/完整度/硬约束/三视图排序）
    ├── verify_rules.py 房源承诺×合同条款的确定性比对
    ├── rules.py        合同风险规则库（一期 10 条，继承自合同风险雷达）
    ├── convert.py      ORM ↔ API 模型
    ├── llm/            LangChain 结构化输出 + mock 确定性实现 + grounding 校验
    └── flows/          import / contract / recommend / verify / chat 五条业务流程
```

## 与选型文档的偏差

见 `doc/plan/后端-v1.1-接口契约.md` §8（SQLite 默认、进程内 RunManager 替代 ARQ+Redis、本地存储、启动建表替代 alembic）。
