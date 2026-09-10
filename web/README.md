# RentGraph Web（一期前端）

按《原型完善执行文档 v1.1》《RentGraph 技术栈选型（2026）》实现的前端工程，已接入 `server/` 后端
（接口契约见 [`doc/plan/后端-v1.1-接口契约.md`](../doc/plan/后端-v1.1-接口契约.md)）。
UI 与交互以根目录原型 [`租房知识图谱-Agent-Frontend-Protype.html`](../租房知识图谱-Agent-Frontend-Protype.html)
为验收基线（页面结构、文案、状态、动效保持一致）。

两种运行模式：

| 模式 | 说明 |
|---|---|
| `VITE_API_MODE=api`（默认） | 走真实后端：导入解析 / 字段提取 / 推荐 / 核验 / 问答全部由 `server/` 提供的 API + SSE 驱动 |
| `VITE_API_MODE=demo` | 纯本地演示数据与规则（原型口径），用于与原型做像素级回归 |

## 快速开始

```bash
cd web
pnpm install
pnpm dev        # 默认 http://localhost:5173（端口被占用时自动顺延；dev 代理把 /api 与 /healthz 转发到 127.0.0.1:8010）
# 后端需先启动：cd ../server && ./.venv/bin/python -m uvicorn rentgraph.main:app --port 8010
# 只跑本地演示：VITE_API_MODE=demo pnpm dev
pnpm build      # 类型检查 + 生产构建，产物在 web/dist
pnpm preview    # 预览生产构建
```

环境要求：Node.js ≥ 22、pnpm ≥ 11。

## 技术栈

| 领域 | 选型 |
|---|---|
| 核心 | React 19.2 + TypeScript 7 + Vite 8 |
| 样式 | Tailwind CSS 4（`@tailwindcss/vite`）+ Font Awesome 6.5 |
| 状态 | Zustand 5（工作台 / 房源 / 合同 / 会话 / 交互状态） |
| 字体 | Inter + PingFang SC 回退（与原型一致） |

> 说明：原型使用 Tailwind v3 Play CDN，本工程使用 v4，因此在 `src/index.css` 中显式还原了
> v3 色板、`shadow-sm` 与默认边框色，并把 Font Awesome 放入低优先级层，确保像素级一致。

## 后端接线

`src/api/` 是唯一的数据出入口，控制器（`controller.ts`）只调用它：

| 文件 | 职责 |
|---|---|
| `config.ts` | `API_BASE`（默认 `/api/v1`）、`API_MODE`（`api` / `demo`）、运行超时 |
| `client.ts` | 统一 fetch：非 2xx 抛 `ApiError{code,message,hint,status}`，错误码直接驱动界面文案 |
| `sse.ts` | 运行事件订阅：`\r?\n\r?\n` 分帧、按 `run_id` 过滤迟到事件、`Last-Event-ID` 重连、`cancelRun` |
| `adapter.ts` | 后端 DTO ↔ 前端领域类型（`House` / `Contract` / `Preferences` / 核验行） |
| `index.ts` | 高层操作：工作台、导入、确认、偏好、推荐、合同、核验、问答 |

接线点与契约 §5 一一对应：批量/粘贴导入 → `POST /import-batches` + SSE → 字段确认面板（含 evidence / missing / duplicate_of）→ `confirm`；
文件导入（xlsx/xls/csv/md/docx/txt）走真实 multipart 上传；推荐 → `POST /recommendations` + SSE（服务端三视图排序 + 五段解释）；
合同 → `POST /contracts`（粘贴）或 `/contracts/upload` → SSE；核验 → `POST /verifications` + SSE（冲突可点回条款、可定位房源字段）；
问答 → `POST /conversations/{id}/messages` + SSE token，引用渲染为可点 chip。停止/切换会话或房源会调用 `POST /runs/{id}/cancel`。

后端不可用时（健康检查失败或请求报错）界面显示「服务不可用」，并给出可执行的重试提示，不会静默吞掉错误。

## 目录结构

```text
web/src
├─ App.tsx                 # 三区布局 + 抽屉/弹窗挂载 + Esc 关闭
├─ store.ts                # Zustand 全局状态（本次工作台临时数据）
├─ controller.ts           # 业务动作：导入、推荐、核验、问答、任务隔离、流式输出
├─ types.ts                # 房源/合同/会话/偏好等数据模型
├─ data/demo.ts            # 演示种子数据、轻量文本解析、演示合同与条款
├─ lib/
│  ├─ calc.ts              # 完整度 / 缺失字段 / 月度总成本 / 一次性成本
│  ├─ recommend.ts         # 硬约束校验、软偏好评分
│  ├─ verification.ts      # 房源承诺 × 合同条款逐项核验规则
│  ├─ answers.ts           # 上下文租房常识问答（含引用角标）
│  ├─ selectors.ts         # getHouse / getContract / 可比较候选
│  └─ markup.ts            # 上传进度卡等少量 HTML 片段
└─ components/
   ├─ Sidebar / Header / ChatView / HousesView / ContractsView
   ├─ HouseDrawer / ContractDrawer
   ├─ ImportModal / PrefsModal / ConfirmModal / Composer / Toast
   └─ cards/               # 推荐卡、核验卡、步骤卡、特殊状态卡
```

## 与原型一致的验收范围

- 首页第一主任务是房源推荐；候选房源与合同明确标注“仅用于本次工作台”。
- 支持粘贴单条、手动填写、批量粘贴、Excel / Word / 文本文件导入，且都先进入 AI 字段确认。
- 候选比较限制 3—10 套：少于 3 套提示继续添加，超过 10 套提示精简。
- 推荐结果包含理由、取舍、真实成本、信息风险、待确认与下一步，且硬约束变化会真实改变结果。
- 目标房源绑定合同后，展示“房源承诺 / 合同条款 / 待确认事项”逐项核验，可定位房源字段与合同原文。
- 租房常识问答优先引用当前合同与房源，无依据时降级为通用建议。
- 流式输出、停止、重新生成、切换会话 / 房源时的任务隔离，以及加载、失败、空态等状态均可回放。

## 已知演示口径

- 上述「演示解析」只存在于 `VITE_API_MODE=demo`；`api` 模式下合同条款、房源解析、核验与问答都来自后端真实结果。
- `api` 模式下 `.xlsx / .xls / .csv / .md / .docx / .txt` 全部由后端解析（表格走确定性列名映射），`.doc` 需另存为 `.docx`。
- 图片与扫描件 OCR、外部平台实时同步、长期保存与跨设备同步均未实现，界面按“规划能力”标注。
- 仅通过输入框粘贴房源文本时，原型会在确认弹窗被遮挡的情况下直接提示确认；本实现为让该路径可用，
  在 `showConfirm` 中会确保导入弹窗打开（这是 demo 模式与原型的唯一有意偏差）。
