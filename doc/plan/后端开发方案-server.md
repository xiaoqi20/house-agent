# 后端开发方案（server/ · 一期合同风险雷达）

> 版本：v1.0 ｜ 2026-09-06 ｜ 上游文档：`doc/plan/一期方案-合同风险雷达.md`、`doc/arch/技术栈选型-前后端分离.md`
> API 契约与 PRD §3 一期功能一一对应；前端接线方式见 §7。

## 0. 本机环境与约束（实测）

| 项 | 状态 | 决策 |
|----|------|------|
| Python | 3.11.9（官方安装版） | 一期以 3.11 为基线（FastAPI/Pydantic/SQLAlchemy 全兼容）；不强行升 3.12，避免网络下载新解释器 |
| uv | 未安装 | 暂不装，用 venv + pip |
| Docker | 29.3.1 ✅ | Postgres 16 用 docker compose 起 |
| pip 网络 | 官方 PyPI **TLS 被重置**；清华源可用 | `server/.pip.conf` 固定 tuna 源（用 `PIP_CONFIG_FILE=$PWD/.pip.conf` 方式引用，勿用 `-c`，那是 constraints） |
| Docker 镜像 | Docker Hub 不可达 | 经 `docker.m.daocloud.io/library/postgres:16-alpine` 拉取后 retag |
| API 端口 | 本机 :8000 已被其他进程占用 | **后端固定 :8010**，前端 proxy 已同步 |
| SQLAlchemy async | macOS arm64 不自动装 greenlet（platform marker 坑） | 依赖显式声明 `greenlet>=3.1` |
| PG 容器 | 随 Docker 重启会 Exited | 开发前 `docker compose up -d db`（无自动恢复） |
| SSE 分帧 | sse-starlette 用 `\r\n\r\n` 分帧 | 前端解析器必须用 `/\r?\n\r?\n/`，否则永远收不到事件（已踩坑） |
| LLM | ✅ 已配置 qwen3.8-flash（百炼 MaaS，key 同步自 ~/.zshrc） | OpenAI SDK 兼容端点；`.env` 字段 llm_base_url / llm_api_key |

## 1. 版本矩阵（2026 稳定版，tuna 源实测）

| 包 | 版本 | 用途 |
|----|------|------|
| fastapi | 0.141.1 | Web 框架 |
| uvicorn | 0.52.4 | ASGI server |
| pydantic | 2.13.5 | 请求模型 + **LLM 输出契约（同一工具链）** |
| pydantic-settings | 2.x | 配置 |
| sqlalchemy | 2.0.52 | ORM（async） |
| alembic | 1.19.2 | 迁移 |
| asyncpg | 0.31.0 | PG 驱动 |
| pdfplumber | 0.11.10 | PDF 文字层提取 |
| openai | 3.8.0 | LLM 统一 client（指向百炼 MaaS qwen3.8-flash） |
| httpx | 0.28.1 | 测试 client |
| sse-starlette | 3.4.11 | SSE 事件流（解析进度 + 流式回答） |
| python-multipart | 0.0.32 | 文件上传 |
| pyjwt | 2.13.0 | 鉴权 token |
| slowapi | 0.1.10 | 限流 |
| structlog | 26.1.0 | 结构化日志 |
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 | 测试 |
| ruff | 0.16.6 | lint + format |
| Postgres（docker 镜像） | 16-alpine | 库 |

## 2. 目录结构

```
server/
├── pyproject.toml          # uv 无关，PEP 621 + ruff 配置
├── .pip.conf               # 锁清华源
├── .env.example
├── docker-compose.yml      # postgres:16-alpine（宿主端口 5433，避开本机已有 5432）
├── alembic.ini / migrations/
├── src/rentgraph/
│   ├── main.py             # FastAPI app 装配（CORS、限流、路由、OpenAPI 导出）
│   ├── config.py           # Settings(pydantic-settings)
│   ├── db.py               # async engine / sessionmaker
│   ├── models.py           # contracts / clauses / risks / conversations
│   ├── schemas/            # API 模型 + ClauseExtraction(LLM 契约)
│   ├── services/
│   │   ├── ingest.py       # ① 导入：paste/pdfplumber → raw_text
│   │   ├── extract.py      # ② 抽取：LLM + JSON Schema → clauses 表
│   │   ├── rules.py        # ③ 规则库（一期 10 条，声明式）
│   │   ├── analyze.py      # 编排 ①→②→③ + SSE 进度事件
│   │   ├── chat.py         # 问答：引用 clauses，grounding 校验
│   │   └── report.py       # 话术/健康度分
│   ├── api/                # 路由：contracts / chat / auth
│   └── scripts/eval_risk.py
├── tests/
└── uploads/                # 本地文件存储（Storage 抽象后）
```

## 3. 数据模型（与方案文档一致 + 会话表）

- `contracts(id, user_id, filename, source_type[paste|pdf], raw_text, health_score, status[uploaded|analyzing|done|failed], error, created_at)`
- `clauses(id, contract_id FK, clause_no, clause_type, title, raw_text, amount, months, date_from, date_to, party_liable, extra JSONB)`
- `risks(id, contract_id FK, clause_id FK, level[high|medium|low], rule_id, title, reason, suggestion, negotiation_script)`
- `conversations(id, user_id, title, created_at)` / `messages(id, conversation_id, role, content JSONB)` — 消息 content 直接存前端消息卡的富结构（file/progress/report 等同构）

状态机：`uploaded → analyzing → done | failed`；analyze 幂等可重试。

## 4. API（前缀 /api/v1，对齐 arch 文档 §3）

```
POST /auth/sms · POST /auth/login                    # 一期：固定验证码 000000（演示）
GET  /contracts
POST /contracts                        {text} | multipart file
GET  /contracts/{id}                   详情
GET  /contracts/{id}/text              原文抽屉：条款列表 + 风险标记
POST /contracts/{id}/analyze           SSE: event progress/token/done/error
GET  /contracts/{id}/risks             风险报告卡数据
POST /chat                             SSE 流式问答
GET  /conversations
```

SSE 事件载荷：
- `progress`：`{step: "parse|extract|rules", index, label, status:"active|done"}` — 驱动前端 checklist
- `error`：`{code, message}` — 如 PDF 无文字层 → 前端引导粘贴文本
- `done`：`{contract}` — 完成后前端拉取 risks

## 5. 核心链路设计

### ① ingest
`extract_pdf(path)`：pdfplumber 逐页 `extract_text()`；总字符 <200 判定"无文字层"→ 抛 `NoTextLayer`（API 422），提示粘贴。粘贴文本清洗空白后入库。

### ② extract（LLM）
- 一次调用：合同全文（截断 ≤12k tokens）→ `ClauseExtraction`（pydantic：`clauses: list[Clause]`，枚举 `clause_type`）
- `temperature=0`，`response_format={"type":"json_object"}`，schema 内嵌 prompt
- 校验失败重试 1 次；**条款原文必须能在 raw_text 中定位**（子串匹配），否则丢弃该条（防幻觉）
- mock 模式：`LLM_PROVIDER=mock` 时走正则条款切分（无 key 也能全链路跑通，前端联调不阻塞）

### ③ rules（声明式）
```python
Rule(id="over-penalty", level="high", clause_type="违约金",
     when=lambda c: (c.months or 0) > 1,
     title="违约金过高", reason=..., suggestion=...)
```
一期 10 条（见方案文档 §5）；输出 risks 时强制携带 `clause_id`（grounding）。
健康度分：`100 - Σ扣分(高 12/中 6/低 3)`，下限 0。

### chat
一期实现：按问题关键词检索该用户最新合同 clauses（SQL ILIKE + clause_type 匹配），拼引用上下文喂 LLM，输出要求 `[第N条]` 标注；后端解析标注并校验条款存在，不存在则剔除重排。LLM 不可用时降级返回模板答案（与前端 mock 文案一致）。

## 6. 鉴权 / 安全 / 成本

- **文件与存储（一期已实现）**：`POST /contracts/upload` 白名单 `.pdf/.txt/.png/.jpg/.jpeg/.webp`；一律先落 `LocalStorage`（`uploads/YYYYMM/…`，`services/storage.py` 定义 `Storage.save/local_path` 接口），`contracts.storage_key` 记录；图片无 OCR → 仅存档 + `status=uploaded` + 提示文案；`GET /contracts/{id}/file` 直出文件（二期换 OSS：实现同一接口，/file 改 302 签名 URL，前后端与库表不变）
- **前端上传入口**：📎/ 选择、输入框粘贴（剪贴板图片/文件）、拖拽进输入框；选中即显示在输入框上方预览卡（图片缩略图/文件名+大小，可移除），点"发送并上传"才真正提交

- JWT（access 2h + refresh 30d），`user_id` 单租户够用；一期短信验证码 mock（固定 000000）
- 合同文本仅上传者可见，查询一律带 `user_id` 条件
- LLM 成本预算：每合同一次抽取（约 ¥0.01 量级）；chat 每问一次；设置每用户日配额（slowapi）
- 上传限制 50MB、类型白名单（pdf/txt/docx 一期只放 pdf/txt）

## 7. 前端接线（替换 mock 的顺序）

1. 后端导出 `server/openapi.json`（main.py 启动落盘）→ 前端 `pnpm gen:api`（orval，已配好）
2. 先接 `POST /contracts` + `GET /contracts/{id}/text`（抽屉真实数据）
3. 再接 `POST /contracts/{id}/analyze` SSE：把 progress 事件映射到现有 checklist 消息
4. chat SSE 替换本地 `pickAnswer`
5. `src/data/contract.ts` 只保留 mock 模式兜底

## 8. 里程碑（与总体 W1-W3 对应）

| 步骤 | 交付 | 验收命令 |
|------|------|----------|
| S1 骨架 ✅ | 目录 + pyproject + compose + healthz + CORS + 建表 | `pytest` 绿 + `curl :8010/healthz` + POST/GET contracts 落库 |
| S2 链路 ✅ | ingest + extract(mock) + 10 条规则 + analyze SSE + /text /risks | `pytest`；curl SSE 三步 progress→done；risks 带条款号 grounding |
| S3 真 LLM ✅ | 抽取走 **qwen3.8-flash**（百炼 MaaS，`server/.env` LLM_PROVIDER=openai；字段名 llm_* 避开全局 OPENAI_API_KEY 冲突）；规则版 chat 已上线 | 单份抽取 ~55s（思考模型）；`evals/report-llm.md` |
| S4 前端接线 ✅ | orval(fetch) 生成 client；上传/粘贴/SSE checklist/风险卡/抽屉/聊天全部走真实 API | 浏览器实测：7 条款 7 风险（高3中3低1）健康度 43；"押金不退"引用第 6 条原文 |
| S5 评测 ✅ | `evals/generate.py` 20 份合成合同+自动标注；`scripts/eval_risk.py` 跑分 | mock：P100/R100；**qwen3.8-flash：P100/R100/F1 100（TP=91）**，延迟 55s/份 |

## 10. 评测结论与诚实边界

- 当前 20 份为**模板化合成语料**（`evals/note` 已注明）：证明的是"LLM 契约抽取 + grounding 校验 + 规则引擎"管线正确，不代表对真实合同的泛化能力
- 真实语料升级路径：收集 20 份脱敏真实合同放入 `evals/contracts/`，按同格式补 `ground_truth.json`，重跑 `eval_risk.py` 即得对外可宣称的数字
- 已发现并修复的真实问题：mock 分类器"标题劫持"（解除条款含"押金不退"被误分押金类）、`db.get` 不预加载关系、SSE `\r\n` 分帧
- 思考模型延迟 55s/份 → 生产可试 `enable_thinking:false` 或换 flash 非思考档；成本：每份合同一次调用

## 9. 明确不做

LangChain/CrewAI、Neo4j、向量库、Celery/Redis、WebSocket、OCR、多租户、计费。
