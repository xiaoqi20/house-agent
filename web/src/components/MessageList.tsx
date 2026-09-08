import {
  Bot,
  CircleCheck,
  CircleDashed,
  FileText,
  LoaderCircle,
} from "lucide-react";
import type { ReactNode } from "react";
import type { Cite } from "@/api/model";
import type { ChatMsg, Step } from "@/types";
import { useChat } from "@/stores/chatStore";
import { RiskReportCard } from "@/components/RiskReportCard";

type Group =
  | { key: string; type: "single"; msg: ChatMsg }
  | { key: string; type: "files"; items: ChatMsg[] };

function groupMessages(messages: ChatMsg[]): Group[] {
  const groups: Group[] = [];
  for (const m of messages) {
    const prev = groups[groups.length - 1];
    if (
      m.role === "user" &&
      (m.kind === "file" || m.kind === "files") &&
      prev?.type === "files"
    ) {
      prev.items.push(m);
    } else if (m.role === "user" && (m.kind === "file" || m.kind === "files")) {
      groups.push({ key: m.id, type: "files", items: [m] });
    } else {
      groups.push({ key: m.id, type: "single", msg: m });
    }
  }
  return groups;
}

export function MessageList() {
  const messages = useChat((s) => s.messages);
  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
      {groupMessages(messages).map((g) =>
        g.type === "files" ? (
          <FileGroup key={g.key} items={g.items} />
        ) : (
          <MessageItem key={g.key} msg={g.msg} />
        ),
      )}
    </div>
  );
}

function UserAvatar() {
  return (
    <div className="w-7 h-7 rounded-full bg-brand-100 border border-gray-200 flex items-center justify-center text-brand-700 text-[9px] font-bold shrink-0 mt-0.5">
      我
    </div>
  );
}

/** 连续发送的图片：并排缩略图（主体即图片），文件名小字角注；文档：单行小卡 */
interface FileEntry {
  name: string;
  contractId?: number;
  mime?: string;
}

function FileGroup({ items }: { items: ChatMsg[] }) {
  const entries: FileEntry[] = items.flatMap((m) =>
    m.kind === "files"
      ? (m.files ?? []).map((x) => ({ ...x }))
      : [{ name: m.text ?? "", contractId: m.contractId, mime: m.mime }],
  );
  return (
    <div className="flex gap-3 flex-row-reverse msg-enter">
      <UserAvatar />
      <div className="flex flex-wrap gap-1.5 justify-end max-w-[85%]">
        {entries.map((m, i) =>
          m.contractId && m.mime?.startsWith("image/") ? (
            <img
              key={i}
              src={`/api/v1/contracts/${m.contractId}/file`}
              alt=""
              title={m.name}
              className="max-h-28 max-w-[150px] w-auto h-auto rounded-xl border border-gray-200 shadow-sm object-cover cursor-zoom-in"
            />
          ) : (
            <div
              key={i}
              className="bg-white border border-gray-200 rounded-2xl rounded-tr-sm px-3 py-2 flex items-center gap-2.5 shadow-sm min-w-0 max-w-[240px]"
            >
              <div className="w-8 h-8 rounded-lg bg-red-50 flex items-center justify-center text-red-500 border border-red-100 shrink-0">
                <FileText size={14} />
              </div>
              <div className="min-w-0">
                <div className="text-[12px] font-medium text-gray-900 truncate">
                  {m.name.split("（")[0]}
                </div>
                {m.name.includes("（") && (
                  <div className="text-[10px] text-gray-400">
                    {m.name.split("（")[1]}
                  </div>
                )}
              </div>
            </div>
          ),
        )}
      </div>
    </div>
  );
}

function MessageItem({ msg }: { msg: ChatMsg }) {
  if (msg.role === "user") {
    return (
      <div className="flex gap-3 flex-row-reverse msg-enter">
        <UserAvatar />
        <TextBubble text={msg.text!} />
      </div>
    );
  }

  return (
    <div className="flex gap-3 msg-enter">
      <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center text-white shrink-0 mt-0.5 shadow-sm">
        <Bot size={12} />
      </div>
      <div className="flex-1 min-w-0">
        {msg.kind === "typing" && <TypingBubble />}
        {msg.kind === "progress" && <ProgressBubble steps={msg.steps ?? []} />}
        {msg.kind === "report" && msg.report && (
          <RiskReportCard summary={msg.report} />
        )}
        {msg.kind === "text" && msg.answer && (
          <AnswerBubble answer={msg.answer} />
        )}
      </div>
    </div>
  );
}

/** 引用条款：必须是后端校验过的真实条号，点击直接定位抽屉原文 */
function CiteChips({
  cites,
  contractId,
}: {
  cites: Cite[];
  contractId: number;
}) {
  const openContract = useChat((s) => s.openContract);
  return (
    <div className="flex flex-wrap gap-1.5 mt-2.5">
      {cites.map((c) => (
        <button
          key={c.clause_no}
          onClick={() => openContract(contractId, c.clause_no)}
          title={c.title ? `${c.title} · 点击定位原文` : "点击定位原文"}
          className="inline-flex items-center gap-1 text-[11px] font-medium text-brand-700 bg-brand-50 hover:bg-brand-100 border border-brand-100 rounded-full px-2 py-0.5 transition-colors"
        >
          <FileText size={10} />第 {c.clause_no} 条
          {c.title ? ` ${c.title}` : ""}
        </button>
      ))}
    </div>
  );
}

/** 正文里的 [第N条] 不裸显示，渲染成小圆圈角标（上标），点击定位原文 */
const INLINE_CITE_RE = /\[第\s*(\d+)\s*条\]/g;

function InlineCitedText({
  text,
  contractId,
}: {
  text: string;
  contractId: number | null;
}) {
  const openContract = useChat((s) => s.openContract);
  const parts: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(INLINE_CITE_RE)) {
    const no = Number(m[1]);
    if (!Number.isFinite(no)) continue;
    parts.push(<span key={`t${last}`}>{text.slice(last, m.index)}</span>);
    parts.push(
      <button
        key={`c${m.index}`}
        onClick={() => contractId != null && openContract(contractId, no)}
        disabled={contractId == null}
        title={`第 ${no} 条 · 点击定位原文`}
        className="mx-0.5 -mt-1 inline-flex h-[15px] min-w-[15px] items-center justify-center rounded-full border border-brand-200 bg-brand-50 px-[3px] align-super text-[9px] font-bold leading-none text-brand-700 transition-colors hover:bg-brand-100 disabled:cursor-default"
      >
        {no}
      </button>,
    );
    last = m.index + m[0].length;
  }
  if (!parts.length) return <>{text}</>;
  parts.push(<span key="tail">{text.slice(last)}</span>);
  return <>{parts}</>;
}

function AnswerBubble({ answer }: { answer: NonNullable<ChatMsg["answer"]> }) {
  const cites = answer.cites ?? [];
  const contractId = answer.contract_id ?? null;
  return (
    <div className="text-[13px] text-gray-800 leading-relaxed bg-gray-50 border border-gray-100 rounded-2xl rounded-tl-sm px-4 py-3">
      <p className="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5">
        <CircleCheck size={14} className="text-green-500" /> {answer.cite}
        {answer.degraded && (
          <span className="text-[10px] font-normal text-amber-600 bg-amber-50 border border-amber-100 rounded px-1.5 py-0.5">
            {answer.mode === "llm"
              ? "模型未能引用到具体条款"
              : "模型不可用，按条款关键词检索"}
          </span>
        )}
      </p>
      {answer.paras.map((p, i) => (
        <p key={i} className={i > 0 ? "mt-2.5" : ""}>
          <InlineCitedText text={p} contractId={contractId} />
        </p>
      ))}
      {cites.length > 0 && contractId != null && (
        <CiteChips cites={cites} contractId={contractId} />
      )}
    </div>
  );
}

function TextBubble({ text }: { text: string }) {
  return (
    <div className="max-w-[85%] text-[13px] text-white leading-relaxed bg-brand-500 rounded-2xl rounded-tr-sm px-4 py-3 shadow-sm whitespace-pre-line">
      {text}
    </div>
  );
}

function TypingBubble() {
  return (
    <div className="bg-gray-50 border border-gray-100 rounded-2xl rounded-tl-sm px-4 py-3.5 inline-flex items-center gap-1.5">
      <span className="typing-dot w-1.5 h-1.5 rounded-full bg-gray-400 inline-block" />
      <span className="typing-dot w-1.5 h-1.5 rounded-full bg-gray-400 inline-block" />
      <span className="typing-dot w-1.5 h-1.5 rounded-full bg-gray-400 inline-block" />
    </div>
  );
}

function StepIcon({ status }: { status: Step["status"] }) {
  if (status === "done")
    return <CircleCheck size={15} className="w-4 shrink-0" />;
  if (status === "active")
    return <LoaderCircle size={15} className="w-4 shrink-0 animate-spin" />;
  return <CircleDashed size={15} className="w-4 shrink-0 text-gray-300" />;
}

/** checklist 先画三个灰圈，再按 SSE 推进（方案 §4：不要空列表等事件） */
function ProgressBubble({ steps }: { steps: Step[] }) {
  return (
    <div className="bg-gray-50 border border-gray-100 rounded-2xl rounded-tl-sm px-4 py-3.5 space-y-2 font-medium">
      {steps.map((st) => (
        <div
          key={st.index}
          className={`flex items-center gap-2.5 text-[13px] ${
            st.status === "done"
              ? "text-green-600"
              : st.status === "active"
                ? "text-gray-800"
                : "text-gray-400"
          }`}
        >
          <StepIcon status={st.status} />
          {st.label}
        </div>
      ))}
    </div>
  );
}
