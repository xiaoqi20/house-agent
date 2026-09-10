# 一期验收清单回执（PRD §11 × 证据）

> 生成时间：2026-09-10 ｜ 对应基线：[原型完善执行文档-v1.1](../doc/prd/原型完善执行文档-v1.0.md) §11
> 证据类型：**A** = 端到端验收脚本（`server/scripts/acceptance_v11.py`，报告 `evals/report-v11.md` / `report-v11-llm.md`）
> **T** = 自动化测试（`server/tests/`，131 个用例，`pytest -q` 全绿）
> **B** = 浏览器实测（Chrome via agent-browser，截图 `/tmp/rg-w3-check-*.png`）

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 首页第一主任务是房源推荐，不是合同审查 | ✅ | B：首页 hero 下方的第一张卡是「添加房源 / 批量导入 / 开始筛选」，合同入口退到次操作行；A：`创建workspace`→导入→推荐的顺序即主链路 |
| 2 | 支持粘贴、手动填写、批量粘贴、Excel / Word / 文本文件导入 | ✅ | T：`test_file_upload_parses_real_drafts`（xlsx/csv/md/txt 各 4 套真实解析）、`test_paste_batch_streams_to_done_with_real_drafts`；A：「识别房源条数 / 租金字段提取」；B：批量粘贴 5 套 → 识别 5 套 |
| 3 | 导入后先展示 AI 提取字段，用户确认或修改租金/押金/物业费/通勤/户型 | ✅ | T：`test_unconfirmed_drafts_do_not_enter_recommendation`、`test_confirm_persists_houses_with_continuous_numbers_and_duplicate_hint`；B：确认面板显示 5800 / 押一付一 / 物业费待确认 / 35 / 一居 + 原文证据 + 字段依据 |
| 4 | 能查看、搜索、筛选、打开候选房源详情 | ✅ | B：候选列表 5 套（含搜索、全部/整租/合租/独立卫浴/信息不完整/已放弃筛选、5 种排序）；T：`test_paste_batch_streams_to_done_with_real_drafts` 覆盖列表接口 |
| 5 | 详情展示数据来源、信息完整度、待核实，不承诺真实有效 | ✅ | T：`test_...`（`/houses` 返回 `source_label`/`completeness`/`missing`/`evidence`）；A：「接口文案无未实现承诺」；B：H1 完整度 83%、缺：物业费、区域 |
| 6 | 比较范围明确限制 3—10 套 | ✅ | T：`test_confirm_over_ten_houses_rejected`（TOO_MANY_HOUSES）、`test_about_window_flags_under_three_candidates`；A：「推荐少于 3 套提示」；B：卡片显示「当前 5 套候选，在 3—10 套比较区间内」 |
| 7 | 能设置硬约束和软偏好 | ✅ | T：`test_preferences_version_increments`；B：筛选偏好弹窗（预算/通勤/独卫/合租 + 5 个软偏好标签），保存后偏好版本递增（推荐文案「第 3 版偏好」） |
| 8 | 推荐结果包含理由、取舍、真实成本、风险和下一步 | ✅ | T：`test_explanation_and_about_are_keyed_by_house_id`；A：「推荐包含理由/取舍/风险/待确认/下一步」；B：推荐卡「推荐理由 / 不足与取舍 / 真实成本 ≈4,650 元 / 待确认 / 下一步按钮」 |
| 9 | 修改预算、通勤或偏好后结果真实变化 | ✅ | T：`test_budget_change_updates_verdict`、`test_commute_change_reorders_mix_view`、`test_snapshot_does_not_follow_new_preferences`；A：「改预算后结果变化」「改通勤后结果变化」「旧报告保留快照」 |
| 10 | 推荐结果能打开对应房源详情，不串到其他房源 | ✅ | T：`test_paste_batch_streams_to_done_with_real_drafts`（house id 稳定）；B：卡片「查看详情」打开抽屉，抽屉头部为同一房源编号 |
| 11 | 选定房源后可进入绑定的合同核验流程 | ✅ | B：点「绑定合同」→ 出现「上传合同 PDF / 粘贴合同文本」→ 发送合同后自动核验；T：`test_verification_requires_house_and_contract` |
| 12 | 房源承诺与合同条款逐项对照 | ✅ | T：`test_scene2_conflicts_locate_clause_and_no_inference`；A：「至少 3 个冲突项」；B：核验表「押金/付款方式 · 第 5 条 · 冲突」等逐行展示，摘要「3 项冲突、2 项未约定、5 项无法判断、1 项一致」 |
| 13 | 合同风险可定位原文，并能回到房源字段 | ✅ | T：`test_scene2_items_carry_anchor_and_negotiation_has_clause_numbers`（`anchor` + `clause_no` + `page` + `char_start/end`）；T：`test_paste_contract_clauses_carry_numbers_and_spans`；B：核验项可点开条款、可「定位房源字段」 |
| 14 | 租房常识问答能使用当前房源和合同上下文 | ✅ | T：`test_context_question_cites_existing_clause`、`test_removing_contract_stops_referencing_your_contract`；A：「问答引用当前合同条款」「移除合同后不再声称基于合同」；B：「结合你的合同与房源 · 引用 第 9 条」并给出条款原文 |
| 15 | 流式输出、停止、重试、切换会话不会串线 | ✅ | T：`test_concurrent_runs_keep_their_own_results_and_events`、`test_cancelling_one_run_does_not_affect_the_other`、`test_finished_old_run_does_not_write_into_new_conversation`、`test_cancel_run_stops_without_done`、`test_sse_frames_and_finishes_on_terminal`；A：「取消后运行状态为 cancelled」 |
| 16 | 上传失败、解析失败、信息缺失、无匹配都有明确状态 | ✅ | T：`test_scanned_pdf_returns_no_text_layer`、`test_text_too_short_rejected`、`test_image_upload_returns_ocr_unsupported_and_status_failed`、`test_unsupported_doc_upload_rejected`、`test_no_candidates_returns_no_drafts`；A：「过短合同文本被拒」「无效工作台返回 404」 |
| 17 | 页面没有未实现的文件格式、隐私和分享承诺 | ✅ | 全仓文案检查：`真实有效 / 已验证房源 / 仅自己可见 / 我的房源库 / 平台认证 / 最新库存` 均无命中（A：「接口文案无未实现承诺」）；侧栏/页脚改为「本次工作台临时数据（有效期 72 小时）」；合同入口标注「PDF（文字版）/ Word(.docx) / 文本文件；图片仅存档，暂不做 OCR」 |
| 18 | 三个演示场景可以从头到尾独立重放 | ✅ | A：`scripts/acceptance_v11.py` 42/42（mock 与真实模型各跑一遍）；T：`test_scene2_*`、`test_three_views_order_matches_domain_rules`；B：本轮浏览器实测依次走通场景 1（导入→确认→偏好→推荐）、场景 2（合同→核验→条款定位）、场景 3（上下文问答） |

## 未达标项

无。

## 备注

- 自动化覆盖：`pytest -q` = 131 passed（约 7s，离线确定性）；端到端验收脚本 42 项检查；两者都可重复执行。
- 真实模型（百炼 qwen3.8-flash）已跑通全链路：`evals/report-v11-llm.md`。
- 与选型文档的差异（SQLite 默认、进程内 RunManager、未接 LangGraph 状态图与 Orval）逐条记录在
  [`doc/plan/后端-v1.1-接口契约.md`](../doc/plan/后端-v1.1-接口契约.md) §8。
