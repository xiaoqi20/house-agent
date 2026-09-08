import { create } from "zustand";
import {
  chatApiV1ChatPost,
  contractRisksApiV1ContractsContractIdRisksGet,
  createContractApiV1ContractsPost,
  getContractApiV1ContractsContractIdGet,
  listContractsApiV1ContractsGet,
  uploadContractApiV1ContractsUploadPost,
} from "@/api/generated/rentGraphAPI";
import { errorMessage, fromSseError, toApiError } from "@/api/errors";
import { ssePost } from "@/api/sse";
import type { ContractOut } from "@/api/model";
import type { ChatMsg, Step } from "@/types";

interface ChatState {
  started: boolean;
  title: string;
  messages: ChatMsg[];
  /** 当前绑定的合同：追问只能问它（一期方案 §2.2） */
  contractId: number | null;
  drawerOpen: boolean;
  drawerContractId: number | null;
  focusClause: number | null;
  toast: string | null;
  reset: () => void;
  send: (text: string) => void;
  uploadFile: (file: File, displayName?: string) => void;
  uploadImages: (files: File[]) => void;
  reviewLatest: () => void;
  reviewContract: (contractId: number) => void;
  openContract: (contractId: number, clauseNo?: number | null) => void;
  closeContract: () => void;
  showToast: (msg: string) => void;
}

const uid = () => Math.random().toString(36).slice(2, 10);
/** 与后端 ContractCreate(min_length=50) 对齐；无条号但明显是一篇长文也当合同处理，交给后端如实报错 */
const PASTE_MIN = 50;
const PASTE_LONG = 300;
const CLAUSE_RE = /第[一二三四五六七八九十百零〇\d]+条/;
const REVIEW_RE =
  /(审查|检查|看一下|看下|评估|风险).{0,12}(合同|条款)|(合同|条款).{0,12}(审查|检查|风险)/;

const CHECKLIST: Step[] = [
  { index: 0, label: "解析文档", status: "pending" },
  { index: 1, label: "抽取条款", status: "pending" },
  { index: 2, label: "匹配规则库", status: "pending" },
];

let toastTimer: number | undefined;

const isContractPaste = (t: string) =>
  t.length >= PASTE_MIN && (t.length >= PASTE_LONG || CLAUSE_RE.test(t));

export const useChat = create<ChatState>((set, get) => {
  const push = (msg: ChatMsg) =>
    set((s) => ({ messages: [...s.messages, msg] }));
  const remove = (id: string) =>
    set((s) => ({ messages: s.messages.filter((m) => m.id !== id) }));
  const patch = (id: string, updater: (m: ChatMsg) => ChatMsg) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? updater(m) : m)),
    }));
  const beginThread = (title: string, contractId?: number | null) => {
    if (!get().started) set({ started: true, title });
    if (contractId !== undefined) set({ contractId });
  };

  const failBubble = (cite: string, message: string, extra?: string) =>
    push({
      id: uid(),
      role: "ai",
      kind: "text",
      answer: { cite, paras: extra ? [message, extra] : [message] },
    });

  const analyzeContract = async (contract: ContractOut, userLabel?: string) => {
    beginThread("合同风险审查", contract.id);
    if (userLabel)
      push({
        id: uid(),
        role: "user",
        kind: "file",
        text: userLabel,
        contractId: contract.id,
      });
    const progressId = uid();
    push({
      id: progressId,
      role: "ai",
      kind: "progress",
      steps: CHECKLIST.map((s) => ({ ...s })),
    });
    const upsertStep = (e: Step) =>
      patch(progressId, (m) => {
        const steps = [...(m.steps ?? [])];
        const idx = steps.findIndex((x) => x.index === e.index);
        const next: Step = { ...e, label: e.label || steps[idx]?.label || "" };
        if (idx >= 0) steps[idx] = next;
        else steps.push(next);
        return { ...m, steps };
      });
    let finished = false;
    try {
      await ssePost(`/api/v1/contracts/${contract.id}/analyze`, (ev) => {
        if (ev.name === "progress") upsertStep(ev.data as unknown as Step);
        else if (ev.name === "done") finished = true;
        else if (ev.name === "error") {
          const api = fromSseError(
            ev.data as { code?: string; message?: string },
          );
          remove(progressId);
          const hint =
            api.code === "NO_CLAUSES"
              ? "提示：粘贴时请带上「第 N 条」原文全文，或改用条款更规整的合同。"
              : undefined;
          failBubble("分析失败", api.message, hint);
        }
      });
    } catch (err) {
      remove(progressId);
      failBubble("分析失败", errorMessage(err, "无法连接分析接口"));
      return;
    }
    if (!finished) return;
    try {
      const summary = await contractRisksApiV1ContractsContractIdRisksGet(
        contract.id,
      );
      remove(progressId);
      push({ id: uid(), role: "ai", kind: "report", report: summary });
    } catch (err) {
      remove(progressId);
      failBubble("报告拉取失败", errorMessage(err));
    }
  };

  const ask = (text: string) => {
    const typingId = uid();
    push({ id: typingId, role: "ai", kind: "typing" });
    void (async () => {
      const contractId = get().contractId;
      let answer;
      try {
        answer = await chatApiV1ChatPost({
          question: text,
          contract_id: contractId ?? undefined,
        });
      } catch (err) {
        remove(typingId);
        failBubble("追问失败", errorMessage(err));
        return;
      }
      remove(typingId);
      if (answer.contract_id) set({ contractId: answer.contract_id });
      push({ id: uid(), role: "ai", kind: "text", answer });
    })();
  };

  return {
    started: false,
    title: "对话工作台",
    messages: [],
    contractId: null,
    drawerOpen: false,
    drawerContractId: null,
    focusClause: null,
    toast: null,

    reset: () =>
      set({
        started: false,
        title: "对话工作台",
        messages: [],
        drawerOpen: false,
        focusClause: null,
        contractId: null,
      }),

    send: (text) => {
      if (isContractPaste(text)) {
        beginThread("合同风险审查");
        push({ id: uid(), role: "user", kind: "text", text });
        void (async () => {
          try {
            const contract = await createContractApiV1ContractsPost({
              text,
              filename: "粘贴的合同",
            });
            await analyzeContract(contract);
          } catch (err) {
            failBubble("入库失败", errorMessage(err));
          }
        })();
        return;
      }
      // 演示脚本第 1 步就是在对话框里写「审查刚上传的《房屋租赁合同》」：这类句子走审查，不走问答
      if (REVIEW_RE.test(text)) {
        beginThread("合同风险审查");
        push({ id: uid(), role: "user", kind: "text", text });
        get().reviewLatest();
        return;
      }
      beginThread("合同问答");
      push({ id: uid(), role: "user", kind: "text", text });
      ask(text);
    },

    uploadFile: (file, displayName) => {
      beginThread("合同风险审查");
      const label =
        displayName ??
        `${file.name}（${Math.max(1, Math.round(file.size / 1024))} KB）`;
      void (async () => {
        let contract: ContractOut;
        try {
          contract = await uploadContractApiV1ContractsUploadPost({ file });
        } catch (err) {
          const api = toApiError(err, "上传失败");
          failBubble(
            "上传失败",
            api.message,
            api.needsPaste
              ? undefined
              : "一期支持 PDF / TXT / 图片存档，Word 在二期。",
          );
          return;
        }
        if (contract.source_type === "image") {
          push({
            id: uid(),
            role: "user",
            kind: "file",
            text: label,
            contractId: contract.id,
            mime: file.type,
          });
          failBubble(
            "图片已存档",
            `${file.name || "图片"}已存入服务器 uploads/（LocalStorage；二期平滑升级 OSS，storage_key 接口位不变）。`,
            "拍照/扫描件的文字识别（OCR）二期上线。当前请上传带文字层的 PDF、TXT，或在输入框粘贴合同文本。",
          );
          return;
        }
        await analyzeContract(contract, label);
      })();
    },

    uploadImages: (files) => {
      beginThread("图片存档");
      void (async () => {
        const done: { name: string; contractId: number; mime: string }[] = [];
        const failed: string[] = [];
        await Promise.all(
          files.map(async (file, i) => {
            const name = file.name || `粘贴图片-${i + 1}.png`;
            try {
              const contract = await uploadContractApiV1ContractsUploadPost({
                file,
              });
              done.push({
                name: `${name}（${Math.max(1, Math.round(file.size / 1024))} KB）`,
                contractId: contract.id,
                mime: file.type,
              });
            } catch (err) {
              failed.push(`${name}：${errorMessage(err)}`);
            }
          }),
        );
        if (done.length)
          push({ id: uid(), role: "user", kind: "files", files: done });
        push({
          id: uid(),
          role: "ai",
          kind: "text",
          answer: {
            cite:
              failed.length && done.length
                ? "部分图片已存档"
                : failed.length
                  ? "图片存档失败"
                  : "图片已存档",
            paras: [
              ...(done.length
                ? [
                    `${done.length} 张图片已存入服务器 uploads/（LocalStorage；二期平滑升级 OSS，storage_key 接口位不变）。`,
                  ]
                : []),
              ...failed,
              ...(done.length
                ? [
                    "拍照/扫描件的条款文字识别（OCR）二期上线；当前分析请直接上传带文字层的 PDF/TXT 或粘贴文本。",
                  ]
                : []),
            ],
          },
        });
      })();
    },

    reviewLatest: () => {
      void (async () => {
        let list: ContractOut[] = [];
        try {
          list = await listContractsApiV1ContractsGet();
        } catch (err) {
          get().showToast(errorMessage(err, "后端未连通"));
          return;
        }
        if (!list.length) {
          get().showToast("合同库为空：点 📎 上传合同，或直接粘贴合同全文");
          return;
        }
        await get().reviewContract(list[0].id);
      })();
    },

    reviewContract: (contractId) => {
      void (async () => {
        let contract: ContractOut;
        try {
          contract = await getContractApiV1ContractsContractIdGet(contractId);
        } catch (err) {
          failBubble("打开合同失败", errorMessage(err));
          return;
        }
        beginThread("合同风险审查", contract.id);
        if (contract.source_type === "image") {
          failBubble(
            "这份文件还不能分析",
            contract.error ??
              "图片存档走二期 OCR；当前请上传带文字层的 PDF/TXT 或粘贴文本。",
          );
          return;
        }
        await analyzeContract(contract, contract.filename ?? "我的合同");
      })();
    },

    openContract: (contractId, clauseNo) =>
      set({
        drawerOpen: true,
        drawerContractId: contractId,
        focusClause: clauseNo ?? null,
      }),

    closeContract: () => set({ drawerOpen: false }),

    showToast: (msg) => {
      window.clearTimeout(toastTimer);
      set({ toast: msg });
      toastTimer = window.setTimeout(() => set({ toast: null }), 2400);
    },
  };
});
