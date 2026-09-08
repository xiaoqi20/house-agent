import { useEffect, useRef } from "react";
import { FileText, HandCoins, Shield, ShieldQuestion } from "lucide-react";
import { Composer } from "@/components/Composer";
import { MessageList } from "@/components/MessageList";
import { useChat } from "@/stores/chatStore";

export function Workbench() {
  const started = useChat((s) => s.started);
  const messages = useChat((s) => s.messages);
  const send = useChat((s) => s.send);
  const reviewLatest = useChat((s) => s.reviewLatest);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  return (
    <>
      <div className="flex-1 overflow-y-auto custom-scrollbar" ref={scrollRef}>
        {!started ? (
          <Hero send={send} reviewLatest={reviewLatest} />
        ) : (
          <MessageList />
        )}
      </div>

      {started && (
        <div className="border-t border-gray-100 bg-white p-4 shrink-0">
          <div className="max-w-3xl mx-auto">
            <Composer />
            <p className="text-[10px] text-center text-gray-400 mt-2">
              Agent 基于你的合同图谱回答，内容仅供参考，不构成法律意见
            </p>
          </div>
        </div>
      )}
    </>
  );
}

function Hero({
  send,
  reviewLatest,
}: {
  send: (t: string) => void;
  reviewLatest: () => void;
}) {
  return (
    <div className="min-h-full flex">
      <div className="m-auto flex flex-col items-center w-full px-6 py-10">
        <h1
          className="text-2xl md:text-3xl font-bold text-gray-900 tracking-tight fade-in"
          style={{ animationDelay: ".05s" }}
        >
          你好，我是你的租房合同 Agent
        </h1>
        <p
          className="text-sm text-gray-500 mt-3 mb-10 fade-in"
          style={{ animationDelay: ".1s" }}
        >
          上传一份合同，我会抽取条款、扫描风险，并带你定位到原文
        </p>

        <div
          className="w-full max-w-2xl fade-in"
          style={{ animationDelay: ".15s" }}
        >
          <Composer />
          <p className="text-[11px] text-gray-400 mt-2 px-1">
            粘贴 50
            字以上合同全文会直接进入分析；短文本按提问处理（追问会绑在当前合同上）
          </p>
        </div>

        <div
          className="flex flex-wrap justify-center gap-5 mt-8 mb-4 fade-in px-4"
          style={{ animationDelay: ".2s" }}
        >
          <button
            onClick={reviewLatest}
            className="w-36 h-32 bg-yellow-50 border border-yellow-200 rounded-2xl shadow-sm hover:shadow-md transform -rotate-6 hover:rotate-0 hover:-translate-y-1.5 transition-all duration-300 p-4 flex flex-col text-left group"
          >
            <div className="w-8 h-8 rounded-full bg-yellow-100 flex items-center justify-center text-yellow-600 mb-auto transition-transform group-hover:scale-110">
              <FileText size={14} />
            </div>
            <span className="text-[13px] font-semibold text-yellow-900 leading-snug">
              审查刚上传的
              <br />
              租赁合同
            </span>
          </button>

          <button
            onClick={() => send("违约金条款怎么跟房东谈？")}
            className="w-36 h-32 bg-purple-50 border border-purple-200 rounded-2xl shadow-sm hover:shadow-md transform rotate-3 hover:rotate-0 hover:-translate-y-1.5 transition-all duration-300 p-4 flex flex-col text-left group mt-3"
          >
            <div className="w-8 h-8 rounded-full bg-purple-100 flex items-center justify-center text-purple-600 mb-auto transition-transform group-hover:scale-110">
              <HandCoins size={14} />
            </div>
            <span className="text-[13px] font-semibold text-purple-900 leading-snug">
              违约金条款
              <br />
              怎么谈？
            </span>
          </button>

          <button
            onClick={() => send("押金不退怎么办？")}
            className="w-36 h-32 bg-emerald-50 border border-emerald-200 rounded-2xl shadow-sm hover:shadow-md transform -rotate-3 hover:rotate-0 hover:-translate-y-1.5 transition-all duration-300 p-4 flex flex-col text-left group"
          >
            <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center text-emerald-600 mb-auto transition-transform group-hover:scale-110">
              <Shield size={14} />
            </div>
            <span className="text-[13px] font-semibold text-emerald-900 leading-snug">
              押金不退
              <br />
              怎么办？
            </span>
          </button>
        </div>

        <p className="text-[11px] text-gray-400 mt-10 flex items-center gap-1.5">
          <ShieldQuestion size={11} /> 支持 PDF / TXT / 粘贴文本 · Word 与扫描件
          OCR 在二期
        </p>
        <p className="text-[11px] text-gray-400 mt-1">
          本机演示，未做登录与多租户隔离 · 结论仅供参考，不构成法律意见
        </p>
      </div>
    </div>
  );
}
