import { useState } from "react";
import {
  ArrowRight,
  Check,
  Download,
  MessageSquare,
  ShieldAlert,
} from "lucide-react";
import type { RisksSummary } from "@/api/model";
import { useChat } from "@/stores/chatStore";
import {
  download,
  LEVEL_LABEL,
  negotiationText,
  reportMarkdown,
} from "@/lib/format";

const LEVEL_CLS = {
  high: "bg-red-50 text-red-600 border-red-100",
  medium: "bg-amber-50 text-amber-600 border-amber-100",
  low: "bg-gray-50 text-gray-500 border-gray-200",
} as const;

export function RiskReportCard({ summary }: { summary: RisksSummary }) {
  const openContract = useChat((s) => s.openContract);
  const showToast = useChat((s) => s.showToast);
  const [copied, setCopied] = useState(false);

  const { counts, risks, health_score: health } = summary;
  const parts = (["high", "medium", "low"] as const)
    .filter((lv) => (counts[lv] ?? 0) > 0)
    .map((lv) => `${LEVEL_LABEL[lv].slice(0, 1)} ${counts[lv]}`)
    .join(" / ");

  const script = negotiationText(summary);

  const copyScript = async () => {
    try {
      await navigator.clipboard.writeText(script);
      setCopied(true);
      showToast("谈判话术已复制到剪贴板");
    } catch {
      showToast("复制失败，请手动选择文本");
    }
  };

  const exportReport = () => {
    download(
      `risk-report-${summary.contract_id}.md`,
      reportMarkdown(summary),
      "text/markdown;charset=utf-8",
    );
    showToast("风险报告已导出（Markdown）");
  };

  return (
    <div>
      <div className="text-[13px] text-gray-800 mb-2">
        {risks.length === 0 ? (
          <span>
            合同解析完成，
            <span className="text-green-600 font-medium">未发现风险条款</span>
            ，可以放心签约：
          </span>
        ) : (
          <span>
            合同解析完成，
            <span className="text-red-600 font-medium">
              发现 {risks.length} 项风险（{parts}）
            </span>
            ，点击任意一条可定位原文：
          </span>
        )}
      </div>
      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
        <div className="px-4 py-3 flex items-center justify-between bg-gray-50/80 border-b border-gray-100">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-gray-900">
            <ShieldAlert size={15} className="text-brand-600" /> 风险雷达报告
            {summary.filename && (
              <span className="font-normal text-[11px] text-gray-400 truncate">
                {summary.filename}
              </span>
            )}
          </div>
          <div className="text-[11px] text-gray-500 shrink-0">
            合同健康度{" "}
            <b
              className={
                health !== null && health < 60
                  ? "text-red-600"
                  : "text-amber-600"
              }
            >
              {health ?? "?"}
            </b>{" "}
            / 100
          </div>
        </div>

        {risks.map((r) => {
          const level = r.level as keyof typeof LEVEL_CLS;
          return (
            <button
              key={r.id}
              onClick={() =>
                openContract(summary.contract_id, r.clause_no ?? undefined)
              }
              className="w-full text-left flex items-start gap-3 px-4 py-3 border-t border-gray-100 hover:bg-gray-50 transition-colors first:border-t-0"
            >
              <span
                className={`shrink-0 mt-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded border ${LEVEL_CLS[level]}`}
              >
                {LEVEL_LABEL[level]}
              </span>
              <span className="flex-1 min-w-0">
                <span className="text-[13px] font-semibold text-gray-900">
                  {r.title}
                  <span className="text-[11px] font-normal text-gray-400 ml-1">
                    第 {r.clause_no ?? "?"} 条
                  </span>
                </span>
                <span className="block text-xs text-gray-500 mt-0.5 leading-relaxed">
                  {r.reason}
                </span>
                {r.negotiation_script && (
                  <span className="block text-[11px] text-gray-400 mt-1 line-clamp-1">
                    话术：{r.negotiation_script}
                  </span>
                )}
              </span>
              <ArrowRight size={12} className="text-gray-300 mt-1.5 shrink-0" />
            </button>
          );
        })}

        <div className="px-4 py-3 border-t border-gray-100 flex gap-2">
          <button
            onClick={copyScript}
            disabled={risks.length === 0}
            className="flex-1 bg-brand-500 hover:bg-brand-600 disabled:opacity-40 text-white rounded-lg py-2 text-xs font-medium shadow-sm transition-colors flex items-center justify-center gap-1.5"
          >
            {copied ? <Check size={12} /> : <MessageSquare size={12} />}
            {copied ? "已复制，可直接粘贴给房东" : "复制谈判话术"}
          </button>
          <button
            onClick={exportReport}
            className="flex-1 bg-white border border-gray-200 hover:bg-gray-50 text-gray-700 rounded-lg py-2 text-xs font-medium transition-colors flex items-center justify-center gap-1.5"
          >
            <Download size={12} /> 导出报告（Markdown）
          </button>
        </div>
      </div>
      <p className="text-[10px] text-gray-400 mt-1.5">
        规则命中结果仅供租房决策参考，不构成法律意见。
      </p>
    </div>
  );
}
