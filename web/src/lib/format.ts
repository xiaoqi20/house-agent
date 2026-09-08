import type { RisksSummary } from "@/api/model";

export const LEVEL_LABEL: Record<string, string> = {
  high: "高风险",
  medium: "中风险",
  low: "低风险",
};

export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const hour = Math.floor(min / 60);
  if (hour < 24) return `${hour} 小时前`;
  const day = Math.floor(hour / 24);
  if (day < 30) return `${day} 天前`;
  return new Date(iso).toLocaleDateString("zh-CN");
}

/** 谈判话术：每条风险一段「条号 + 替换文本」，后端已生成，前端只负责排版（开头问候只留一次） */
export function negotiationText(summary: RisksSummary): string {
  const withScript = summary.risks.filter((r) => r.negotiation_script);
  const head = withScript.length
    ? `房东您好，我找人帮我把合同过了一遍，有 ${withScript.length} 处想跟您商量一下：`
    : "房东您好，我找人帮我把合同过了一遍，暂时没发现需要改的条款。";
  const body = withScript
    .map(
      (r, i) => `${i + 1}. ${r.negotiation_script!.replace(/^房东您好，/, "")}`,
    )
    .join("\n\n");
  return [
    head,
    body,
    "以上，您看我理解的有没有偏差？方便的话我们约个时间把合同改一下。",
  ]
    .filter(Boolean)
    .join("\n\n");
}

/** 导出报告：一期做到可读 Markdown 即可（方案 §4，不做真 PDF） */
export function reportMarkdown(summary: RisksSummary): string {
  const { counts, risks, health_score: health } = summary;
  const date = new Date().toLocaleString("zh-CN", { hour12: false });
  const lines = [
    `# 合同风险报告 · ${summary.filename ?? `合同 #${summary.contract_id}`}`,
    "",
    `- 生成时间：${date}`,
    `- 合同健康度：**${health ?? "?"} / 100**`,
    `- 风险统计：高 ${counts.high ?? 0} / 中 ${counts.medium ?? 0} / 低 ${counts.low ?? 0}`,
    "",
    "> 本报告由 RentGraph 基于合同文本自动分析生成，仅供租房决策参考，不构成法律意见。",
    "",
  ];
  if (!risks.length) {
    lines.push(
      "## 结论",
      "",
      "未命中内置风险规则，未发现明显风险条款。签约前仍建议通读全文。",
      "",
    );
  } else {
    lines.push("## 风险清单", "");
    risks.forEach((r, i) => {
      lines.push(
        `### ${i + 1}. ${r.title}（${LEVEL_LABEL[r.level] ?? r.level}）`,
        "",
        `- 位置：${r.clause_no ? `第 ${r.clause_no} 条${r.clause_title ? `「${r.clause_title}」` : ""}` : "未定位条号"}`,
        `- 命中规则：\`${r.rule_id}\``,
        `- 问题：${r.reason}`,
        `- 建议：${r.suggestion}`,
        "",
      );
      if (r.negotiation_script)
        lines.push("发给房东的话术：", "", "> " + r.negotiation_script, "");
    });
    lines.push(
      "## 一并发给房东的修改请求",
      "",
      "```text",
      negotiationText(summary),
      "```",
      "",
    );
  }
  return lines.join("\n");
}

export function download(filename: string, text: string, mime: string) {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
