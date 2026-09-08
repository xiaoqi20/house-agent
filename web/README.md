# rentgraph-web

前端工程：Vite 8 + React 19 + TS 7 + Tailwind 4 + zustand + TanStack Query。
当前为一期演示态（mock 数据在 `src/data/contract.ts`），后端就绪后接 SSE。

```bash
pnpm install
pnpm dev        # http://localhost:5273
pnpm build      # tsc -b && vite build
pnpm gen:api    # orval 从 ../server/openapi.json 生成 API client（后端就绪后）
```

- 原型基准：仓库根目录 `租房知识图谱-Agent-Frontend-Protype.html`（对话即产品，屏幕中心为对话工作台）
- 技术栈与版本矩阵：`doc/arch/技术栈选型-前后端分离.md`
- 包管理用 pnpm（npm 直连官方源在本机网络下会被重置）
