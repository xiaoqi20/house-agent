import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  FileText,
  MessageSquare,
  Network,
  Plus,
} from "lucide-react";
import { useState } from "react";
import { listContractsApiV1ContractsGet } from "@/api/generated/rentGraphAPI";
import { errorMessage } from "@/api/errors";
import { timeAgo } from "@/lib/format";
import { useChat } from "@/stores/chatStore";
import type { ContractStatus } from "@/api/model";

const STATUS_LABEL: Record<ContractStatus, string> = {
  uploaded: "待分析",
  analyzing: "分析中",
  done: "已完成",
  failed: "失败",
};

export function Sidebar() {
  const reset = useChat((s) => s.reset);
  const openContract = useChat((s) => s.openContract);
  const reviewContract = useChat((s) => s.reviewContract);
  const contractId = useChat((s) => s.contractId);
  const started = useChat((s) => s.started);
  const showToast = useChat((s) => s.showToast);
  const [open, setOpen] = useState(true);

  const { data, isLoading, error } = useQuery({
    queryKey: ["contracts"],
    queryFn: () => listContractsApiV1ContractsGet(),
    refetchInterval: 15000,
  });

  return (
    <aside className="w-[240px] bg-gray-50 border-r border-gray-200 flex-col flex-shrink-0 hidden md:flex">
      <div className="h-16 flex items-center px-5">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center text-white shadow-sm">
            <Network size={15} />
          </div>
          <span className="font-bold text-[16px] tracking-tight text-gray-900">
            RentGraph
          </span>
          <span className="px-1.5 py-0.5 bg-gray-200 text-gray-600 text-[10px] font-bold rounded uppercase">
            Beta
          </span>
        </div>
      </div>

      <div className="px-4">
        <button
          onClick={reset}
          className="w-full bg-brand-500 hover:bg-brand-600 text-white px-4 py-2.5 rounded-xl text-sm font-medium shadow-sm transition-colors flex items-center justify-center gap-2"
        >
          <Plus size={14} /> 新建分析
        </button>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 mt-5 space-y-1">
        {started && (
          <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-gray-900 bg-white border border-gray-200 shadow-sm">
            <MessageSquare
              size={15}
              className="w-5 shrink-0 justify-center text-gray-700"
            />{" "}
            当前会话
          </button>
        )}

        <button
          onClick={() => setOpen((v) => !v)}
          className="w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors"
        >
          <span className="flex items-center gap-3">
            <FileText
              size={15}
              className="w-5 shrink-0 justify-center text-gray-400"
            />{" "}
            我的合同
          </span>
          <span className="flex items-center gap-1.5">
            <span className="text-[10px] bg-gray-200 text-gray-600 font-bold px-1.5 py-0.5 rounded">
              {data?.length ?? 0}
            </span>
            <ChevronDown
              size={12}
              className={`text-gray-400 transition-transform ${open ? "" : "-rotate-90"}`}
            />
          </span>
        </button>

        {open && (
          <div className="mb-2">
            {error && (
              <div className="px-3 py-1.5 text-[11px] text-red-500">
                {errorMessage(error, "合同列表加载失败")}
              </div>
            )}
            {isLoading && !error && (
              <div className="px-3 py-1.5 text-[11px] text-gray-400">
                加载中…
              </div>
            )}
            {data && data.length === 0 && (
              <div className="px-3 py-1.5 text-[11px] text-gray-400">
                还没有合同，粘贴或上传一份试试
              </div>
            )}
            <ul className="space-y-0.5">
              {data?.map((c) => (
                <li key={c.id} className="group relative">
                  <button
                    onClick={() =>
                      c.status === "done" || c.status === "failed"
                        ? openContract(c.id)
                        : reviewContract(c.id)
                    }
                    title={c.status === "done" ? "查看原文与风险" : "开始分析"}
                    className={`w-full text-left pl-3 pr-2 py-1.5 rounded-lg transition-colors hover:bg-gray-100 ${
                      contractId === c.id
                        ? "bg-white border border-gray-200"
                        : ""
                    }`}
                  >
                    <div className="text-[12px] text-gray-700 truncate">
                      {c.filename ?? `合同 #${c.id}`}
                    </div>
                    <div className="text-[10px] text-gray-400 flex items-center gap-1.5">
                      <span
                        className={
                          c.status === "done"
                            ? "text-green-600"
                            : c.status === "failed"
                              ? "text-red-500"
                              : "text-gray-400"
                        }
                      >
                        {STATUS_LABEL[c.status]}
                      </span>
                      <span>·</span>
                      <span>{timeAgo(c.created_at)}</span>
                      {c.health_score != null && (
                        <span className="ml-auto text-gray-500">
                          健康度 {c.health_score}
                        </span>
                      )}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="pt-6 text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2 px-3">
          最近对话
        </div>
        <button
          onClick={() => showToast("一期不做会话持久化，当前会话刷新即清空")}
          className="w-full flex items-center gap-2.5 text-left px-3 py-2 rounded-xl text-[13px] text-gray-500 hover:bg-gray-100 truncate transition-colors"
        >
          <MessageSquare size={13} className="shrink-0 text-gray-400" />
          {started ? "当前会话（未保存）" : "暂无会话"}
        </button>
      </div>

      <div className="p-4 border-t border-gray-200 mt-auto">
        <div className="px-2 py-2.5 rounded-xl">
          <div className="text-[13px] font-semibold text-gray-900">
            本机演示
          </div>
          <div className="text-[11px] text-gray-500 mt-0.5 leading-relaxed">
            未做登录与多租户隔离，同一后端的合同彼此可见。
          </div>
        </div>
      </div>
    </aside>
  );
}
