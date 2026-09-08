import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  FileText,
  Highlighter,
  LoaderCircle,
  TriangleAlert,
  X,
} from "lucide-react";
import { contractTextApiV1ContractsContractIdTextGet } from "@/api/generated/rentGraphAPI";
import { useChat } from "@/stores/chatStore";

export function ContractDrawer() {
  const drawerOpen = useChat((s) => s.drawerOpen);
  const drawerContractId = useChat((s) => s.drawerContractId);
  const focusClause = useChat((s) => s.focusClause);
  const closeContract = useChat((s) => s.closeContract);

  const { data } = useQuery({
    queryKey: ["contract-text", drawerContractId],
    queryFn: () =>
      contractTextApiV1ContractsContractIdTextGet(drawerContractId!),
    enabled: drawerOpen && drawerContractId !== null,
  });

  useEffect(() => {
    if (drawerOpen && focusClause) {
      const t = window.setTimeout(
        () =>
          document
            .getElementById(`cl-${focusClause}`)
            ?.scrollIntoView({ behavior: "smooth", block: "center" }),
        350,
      );
      return () => window.clearTimeout(t);
    }
  }, [drawerOpen, focusClause, data]);

  return (
    <>
      <div
        className={`fixed inset-0 bg-black/20 z-30 transition-opacity ${drawerOpen ? "opacity-100" : "opacity-0 pointer-events-none"}`}
        onClick={closeContract}
      />
      <aside
        className={`fixed inset-y-0 right-0 w-full max-w-md bg-white shadow-2xl z-40 transform transition-transform duration-300 flex flex-col ${
          drawerOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="h-16 flex items-center justify-between px-5 border-b border-gray-100 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-lg bg-red-50 flex items-center justify-center text-red-500 border border-red-100 shrink-0">
              <FileText size={16} />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-gray-900 truncate">
                {data?.filename ?? "合同原文"}
              </div>
              <div className="text-[11px] text-gray-500">
                {data ? `已解析 ${data.clauses.length} 项条款` : "加载中…"}
              </div>
            </div>
          </div>
          <button
            onClick={closeContract}
            className="w-8 h-8 rounded-lg hover:bg-gray-100 text-gray-400 flex items-center justify-center shrink-0"
          >
            <X size={15} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar p-6 text-[13px] leading-7 text-gray-600 space-y-5">
          {!data && (
            <div className="flex items-center gap-2 text-gray-400 text-sm pt-8 justify-center">
              <LoaderCircle size={16} className="animate-spin" />{" "}
              正在拉取合同原文…
            </div>
          )}
          {data?.clauses.map((c) => (
            <div key={c.id}>
              <div id={`cl-${c.clause_no ?? c.id}`} />
              <div
                className={c.is_risk ? "pl-3 border-l-2 border-amber-300" : ""}
              >
                <h4 className="text-sm font-semibold text-gray-900 mb-1">
                  {c.title}
                  {c.clause_no != null && (
                    <span className="ml-2 text-[11px] font-normal text-gray-400">
                      第 {c.clause_no} 条
                    </span>
                  )}
                </h4>
                <p>
                  {c.is_risk ? (
                    <mark className="clause">{c.raw_text}</mark>
                  ) : (
                    c.raw_text
                  )}
                </p>
                {(c.risks ?? []).length > 0 && (
                  <ul className="mt-2 space-y-1.5">
                    {c.risks!.map((r) => (
                      <li
                        key={r.id}
                        className="text-[11px] leading-5 flex items-start gap-1.5"
                      >
                        <TriangleAlert
                          size={11}
                          className={`shrink-0 mt-0.5 ${r.level === "high" ? "text-red-500" : r.level === "medium" ? "text-amber-500" : "text-gray-400"}`}
                        />
                        <span>
                          <b className="text-gray-800">{r.title}</b>
                          <span className="text-gray-400"> · {r.reason}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="p-4 border-t border-gray-100 shrink-0 flex items-center gap-2">
          <Highlighter size={14} className="text-amber-500" />
          <span className="text-xs text-gray-500">
            黄色高亮 = Agent
            判定的风险条款；同一条款可能命中多条规则，已全部列出
          </span>
        </div>
      </aside>
    </>
  );
}
