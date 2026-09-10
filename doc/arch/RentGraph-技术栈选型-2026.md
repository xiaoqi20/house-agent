# RentGraph 完整技术栈选型（2026）

> 版本：v1.0  
> 核验日期：2026-09-09  
> 产品依据：[原型完善执行文档-v1.0.md](../prd/原型完善执行文档-v1.0.md)  
> 版本口径：本文列出的依赖均为 2026-09-09 从官方文档、npm 或 PyPI 核验的当前稳定版本。“2026 版本”表示 2026 年当前可用稳定版，不表示每个包都恰好发布于 2026 年。

## 1. 选型结论

采用以下总体组合：

**React SPA + FastAPI 模块化单体 + LangChain/LangGraph 工作流 + PostgreSQL + Redis/ARQ。**

核心原则：

- LangChain 负责模型接入、工具调用和结构化输出。
- LangGraph 负责可暂停、可恢复、可持久化的业务工作流。
- 确定性规则负责硬约束筛选、成本计算和推荐排序。
- LLM 负责非结构化信息提取、语义核验、解释和上下文问答。
- 每项结论都绑定房源、合同及原文证据，不让 Agent 自由生成不可追溯的排名或法律结论。

## 2. 总体架构

```text
React SPA
  |-- REST：工作台、房源、字段确认、偏好、合同
  `-- SSE：解析进度、Agent token、核验进度
          |
          v
FastAPI API（模块化单体）
  |-- LangGraph：导入确认 / 合同核验 / 上下文问答
  |-- 规则服务：硬约束、费用计算、三种排序
  `-- ARQ Worker：文档解析、LLM 调用、报告生成
          |
          v
PostgreSQL 18 + Redis 8 + 临时文件存储
```

一期使用模块化单体，不拆微服务。API 和 Worker 可以分别部署，但共享领域模型、数据库和任务协议。

## 3. 前端技术栈

| 领域 | 选型与版本 | 用途 |
|---|---|---|
| 运行时 | Node.js `24.21.0` LTS、pnpm `11.18.0` | Node 26 当前尚未进入 LTS，生产使用 Node 24 |
| 核心 | React `19.2.8`、React DOM `19.2.8`、TypeScript `7.0.2` | 类型化 SPA |
| 构建 | Vite `8.2.2`、`@vitejs/plugin-react` `6.1.1` | 无 SSR/SEO 需求，不引入 Next.js |
| 路由 | React Router DOM `7.18.3` | 工作台、导入确认、合同定位等页面状态 |
| 服务端状态 | TanStack Query `5.102.8` | 工作台数据、任务状态、缓存和失效刷新 |
| 比较表格 | TanStack Table `9.2.4` | 3-10 套候选房源比较、筛选和排序 |
| UI 状态 | Zustand `5.0.15` | 抽屉、当前标签和输入草稿；不承载服务端业务数据 |
| 数据校验 | Zod `4.5.4` | API 边界和前端表单校验 |
| 表单 | React Hook Form `7.87.0`、Resolvers `5.9.1` | AI 提取字段逐项确认与修改 |
| 样式 | Tailwind CSS `4.3.3`、`@tailwindcss/vite` `4.3.3` | 工作台布局和视觉系统 |
| UI 基础组件 | Radix UI + shadcn/ui 源码组件 | 对话框、抽屉、菜单、标签和表单控件 |
| 图标 | Lucide React `1.43.0` | 操作按钮和状态图标 |
| 文件上传 | react-dropzone `20.1.1` | 拖放、格式、数量和大小校验 |
| PDF 阅读 | pdfjs-dist `6.3.289` | 页码、文本范围和合同原文高亮定位 |
| 流式解析 | eventsource-parser `4.1.0` + Fetch/AbortController | 支持 POST、停止生成和主动取消 |
| 通知 | Sonner `2.0.8` | 成功、失败、取消和重试反馈 |
| API 生成 | Orval `8.30.0` | 根据 FastAPI OpenAPI 生成类型化 client |
| 单元测试 | Vitest `5.0.0`、Testing Library React `16.3.3` | 组件、hooks 和状态测试 |
| 接口模拟 | MSW `2.15.0` | 前端独立开发及错误状态测试 |
| 端到端测试 | Playwright `1.63.0` | 三条 P0 验收链路和任务隔离测试 |
| 格式化 | Prettier `3.9.6` | 前端代码格式化 |

### 3.1 前端状态边界

- TanStack Query 保存工作台、候选房源、合同、报告和运行任务等服务端状态。
- Zustand 只保存抽屉开关、当前视图、未提交草稿等短期 UI 状态。
- 当前房源和当前合同以服务端上下文为准，前端只缓存其 ID，避免刷新或多标签页后对象串线。
- 所有异步响应按 `run_id` 校验；不是当前运行的迟到事件直接丢弃。

## 4. 后端技术栈

| 领域 | 选型与版本 | 用途 |
|---|---|---|
| Python | Python `3.13.15` | 兼顾 2026 支持周期与 AI/PDF 生态兼容性 |
| Web API | FastAPI `0.141.1`、Uvicorn | Async API、文件上传、OpenAPI |
| 数据模型 | Pydantic `2.13.5`、pydantic-settings `2.15.0` | API、配置和 LLM 结构化输出使用同一模型体系 |
| Agent 框架 | LangChain `1.4.0` | 模型接入、工具和结构化输出 |
| 工作流 | LangGraph `1.2.11` | 状态图、interrupt/resume、流式事件和运行隔离 |
| 模型适配 | langchain-openai `1.6.1` | OpenAI 及兼容接口；业务层不直接依赖供应商 SDK |
| 图状态持久化 | langgraph-checkpoint-postgres `3.1.2`、psycopg `3.3.5` | 按 `thread_id` 保存暂停点和恢复状态 |
| ORM | SQLAlchemy `2.0.52`、asyncpg `0.31.0` | 异步领域数据访问 |
| 迁移 | Alembic `1.19.2` | 数据库迁移 |
| 后台任务 | ARQ `0.28.0` | 文档解析、LLM 调用、核验和清理任务 |
| Redis 客户端 | redis-py `8.1.0` | ARQ、取消标记、幂等锁和事件流 |
| SSE | sse-starlette `3.4.11` | 向前端输出进度、token 和终态事件 |
| 文件上传 | python-multipart `0.0.32` | multipart 请求处理 |
| PDF | pdfplumber `0.11.10` | 提取文字层及页码/坐标证据 |
| Word | python-docx `1.2.0` | `.docx` 解析 |
| Excel | openpyxl `3.1.5`、xlrd `2.0.2` | `.xlsx` 和 `.xls` 解析 |
| 对象存储 | boto3 `1.43.90` | 生产接 S3/OSS 兼容存储 |
| 鉴权 | PyJWT `2.13.0`、pwdlib `0.3.1` | 临时工作台令牌；需要账号时可平滑升级 |
| 日志 | structlog `26.1.0` | 结构化日志和运行标识关联 |
| Agent 追踪 | LangSmith `0.12.2` | Prompt、节点耗时、模型调用和评测追踪 |
| 测试 | pytest `9.1.1`、pytest-asyncio `1.4.0`、HTTPX `0.28.1` | API、异步服务和工作流测试 |
| 质量 | Ruff `0.16.6`、mypy `2.3.1` | lint、格式和静态类型检查 |

Python 不选择当前最新的 `3.14.7`，因为 `3.13.15` 对数据库驱动、文档解析和 AI SDK 的兼容面更稳，同时仍处于正式支持周期。

## 5. 基础设施

| 组件 | 推荐版本/方案 | 职责 |
|---|---|---|
| PostgreSQL | `18.6` | 业务数据、JSONB 提取结果、证据坐标、LangGraph checkpoint |
| Redis Server | `8.10.1` | ARQ 队列、运行取消标记、幂等锁、短期 SSE 事件流 |
| 文件存储 | 开发为本地临时目录；生产为 OSS/S3 | 保存原始导入文件和合同，统一通过 Storage 接口访问 |
| `.doc` 转换 | 隔离 Worker 内调用 LibreOffice headless | 转成 `.docx` 后再解析，不在 API 进程中执行 |
| 反向代理 | Nginx 或云负载均衡 | 静态资源、API 代理、上传大小和超时限制 |
| 容器 | Docker Compose 起步 | `web + api + worker + postgres + redis` |

文件对象和数据库记录都必须设置 `expires_at`。定时任务清理临时工作台数据，产品界面不得暗示永久保存或“仅自己可见”。

## 6. LangGraph 工作流

### 6.1 房源导入 `listing_ingestion_graph`

```text
接收输入
  -> 格式与安全校验
  -> 确定性文档解析
  -> LangChain 结构化字段提取
  -> Pydantic 校验与缺失字段计算
  -> interrupt：等待用户确认/修改
  -> Command(resume=确认结果)
  -> 写入本次候选房源
```

未经确认的字段保存在导入草稿中，不能进入推荐模型。

### 6.2 推荐 `recommendation_graph`

```text
加载已确认房源和偏好
  -> 硬约束确定性过滤
  -> 月度总成本与一次性成本计算
  -> 预算 / 通勤 / 综合匹配三套确定性排序
  -> LLM 生成推荐理由、取舍、风险、待确认和下一步
  -> 引用校验
```

排名和费用不能交给 LLM 计算。这样才能保证预算、通勤或是否允许合租发生变化时，结果稳定且可测试地变化。

### 6.3 合同核验 `contract_verification_graph`

```text
解析合同并按页/条款切分
  -> 保存条款文本、页码和字符范围
  -> 提取房源相关约定
  -> 与用户已确认的房源承诺逐项比较
  -> 输出：一致 / 冲突 / 未约定 / 无法判断
  -> 生成修改建议和谈判话术
```

每个核验项必须包含 `house_evidence_id`、`clause_id`、`page_number` 和文本范围。没有匹配条款时必须输出“未约定”，不得推断为合同已经承诺。

### 6.4 上下文问答 `context_qa_graph`

- 只装载当前 `house_id` 和可选的当前 `contract_id`。
- 合同存在时优先引用合同条款，再补充通用知识。
- 每条引用返回 `source_id/page/span`。
- 找不到当前材料依据时明确降级为通用建议。
- 涉及法规时记录来源、适用地区和核实日期，不生成确定性法律结论。

## 7. 数据模型建议

PostgreSQL 至少包含以下表：

- `workspaces`：临时工作台、过期时间和当前上下文。
- `import_batches`：导入来源、原始文件、解析状态和识别数量。
- `houses`：用户确认后的结构化房源字段。
- `house_evidence`：原始描述片段、链接、批次及字段来源。
- `preferences`：硬约束、软偏好及版本。
- `recommendation_runs`：输入快照、排序结果和解释。
- `contracts`：文件、解析状态、绑定房源。
- `contract_clauses`：条款文本、页码、字符位置。
- `verification_items`：房源承诺、合同条款、核验结果和建议。
- `conversations`、`messages`：对话和引用信息。
- `runs`：运行状态、取消状态、错误、`thread_id` 和 `run_id`。

推荐输入必须保存快照，避免用户修改偏好后旧报告看似对应新条件。

## 8. SSE 与任务隔离

采用“先创建任务，再订阅事件”的接口方式：

```text
POST /api/v1/runs                 -> 返回 run_id
GET  /api/v1/runs/{run_id}/events -> SSE，可携带 Last-Event-ID 重连
POST /api/v1/runs/{run_id}/cancel -> 取消运行
```

每个事件至少携带：

```json
{
  "event_id": "...",
  "workspace_id": "...",
  "thread_id": "...",
  "run_id": "...",
  "house_id": "...",
  "contract_id": "...",
  "type": "progress|token|interrupt|done|error|cancelled",
  "data": {}
}
```

Worker 将事件写入带 TTL 和长度限制的 Redis Stream。切换会话、房源或合同后：

1. 前端调用取消接口并关闭旧 AbortController。
2. Worker 在节点边界检查取消标记。
3. 前端只接收当前 `run_id` 的事件。
4. 迟到结果不得写入新的会话或对象。

## 9. API 模块建议

```text
/api/v1/workspaces
/api/v1/import-batches
/api/v1/houses
/api/v1/preferences
/api/v1/recommendations
/api/v1/contracts
/api/v1/verifications
/api/v1/conversations
/api/v1/runs
```

FastAPI 的 Pydantic Schema 是接口事实源。CI 中生成 OpenAPI，再由 Orval 生成前端类型和请求 client；若生成结果有 diff，则 CI 失败。

## 10. 测试策略

- 规则层：硬约束、费用、排序全部使用纯函数单元测试。
- 解析层：为 `.txt`、`.csv`、`.xlsx`、`.xls`、`.docx`、`.doc` 和文字型 PDF 准备固定样本。
- Agent 层：结构化输出做 Schema 测试，合同核验做标注集回归测试。
- API 层：验证幂等、权限、过期、取消和错误映射。
- 前端层：覆盖字段确认、无匹配、上传失败、停止和重试状态。
- E2E：逐条回放产品文档中的三项 P0 场景。
- 隔离测试：旧运行在切换会话后完成，也不能污染当前页面或数据库当前上下文。

## 11. 一期明确不引入

- Next.js：无 SSR、SEO 或 BFF 需求。
- 微服务、Kubernetes、Kafka：一期规模不需要额外运维边界。
- Celery：ARQ 已能覆盖当前异步任务和取消需求。
- WebSocket：当前是服务端单向进度和 token 输出，SSE 足够。
- Neo4j：一期没有独立图谱查询或多跳图算法需求。
- 向量数据库：当前仅有 3-10 套房源和单份目标合同，PostgreSQL 和精确证据定位足够。
- OCR：图片和扫描件识别明确不在一期范围内。
- 自由式多 Agent：主流程需要确定性、可恢复和可验收，不适合多个 Agent 自主协商。

## 12. 依赖锁定与升级规则

- Python 使用 `uv` 管理环境并提交 `uv.lock`。
- 前端使用 pnpm 并提交 `pnpm-lock.yaml`。
- 应用部署严格使用 lockfile，不在镜像构建时浮动升级。
- Docker 镜像固定完整版本和 digest，不使用 `latest`。
- 每月由自动化任务检查依赖更新；LangChain、LangGraph、Pydantic、React、TypeScript 的大版本升级必须单独评估。
- 模型名称、超时、最大 token、温度和重试策略放入配置，不写死在业务代码中。
- Prompt 和结构化输出 Schema 纳入版本控制，并通过标注集回归后再发布。

## 13. 最终决策摘要

这套架构的关键不是“使用 LangChain”，而是明确 LangChain 的边界：

- 能确定性完成的筛选、费用和排序不用 LLM。
- 需要理解文本的提取、语义核验和解释使用 LangChain。
- 需要暂停确认、恢复、追踪和隔离的流程使用 LangGraph。
- 所有 LLM 输出必须经过 Pydantic 校验并携带证据引用。

该组合能够覆盖一期要求的多格式导入、字段确认、3-10 套比较、可解释推荐、合同原文定位、房源承诺核验、上下文问答、SSE 流式输出、停止重试和任务隔离，同时保留后续扩展空间。
