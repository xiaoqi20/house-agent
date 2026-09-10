import { useStore } from './store';
import type {
  Attachment,
  Contract,
  House,
  ImportInputTab,
  ImportTab,
  Message,
  MessageContent,
  PendingRow,
  Preferences,
  RecView,
  SoftKey,
  SourceKey,
  VerificationResult,
} from './types';
import {
  DEMO_BATCH_TEXT,
  DEMO_CONTRACT_TEXT,
  buildBoundContract,
  cloneHouse,
  clonePrefs,
  demoHouses,
  mkContract,
  nextBatchId,
  parseHousesInput,
} from './data/demo';
import { buildSeed, textBubble } from './lib/seeds';
import { answerFor, answerHTML } from './lib/answers';
import { esc, fmt, fmtSize, nid } from './lib/utils';
import { activeHouses, comparableHouses, getContract, getHouse, isLiveHouse } from './lib/selectors';
import { typingDotsHTML, uploadCardHTML } from './lib/markup';
import {
  API_MODE,
  ApiError,
  ask,
  cancelRun,
  confirmBatch,
  contractFromDto,
  deleteContract as deleteContractApi,
  deleteConversation,
  deleteHouse as deleteHouseApi,
  draftToPending,
  ensureConversation,
  ensureWorkspace,
  getBatch,
  getContract as fetchContract,
  getPreferences,
  getRecommendation,
  getVerification,
  importFile,
  importText,
  listContracts,
  listConversations,
  listHouses,
  listMessages,
  messageFromDto,
  patchHouse,
  ping,
  putPreferences,
  recommendationResult,
  resetWorkspace,
  retryContract,
  saveContract,
  setContext as putContext,
  startRecommendation,
  startVerification,
  uploadContract,
  verificationResult,
  waitRun,
  type AnswerDto,
  type BatchDto,
  type ContractDto,
  type HouseDraftDto,
  type RecommendationDto,
  type RunEventDto,
  type VerificationDto,
} from './api';

const get = useStore.getState;
const set = useStore.setState;

// ==================== 通用反馈 ====================
let toastKey = 0;
export function toast(msg: string) {
  set({ toast: { msg, key: ++toastKey } });
}

export function askConfirm(title: string, desc: string, cb: () => void, okText = '删除') {
  set({ confirmModal: { open: true, title, desc, okText, onOk: cb } });
}
export function closeModal() {
  set((s) => ({ confirmModal: { ...s.confirmModal, open: false, onOk: null } }));
}
export function confirmModal() {
  const cb = get().confirmModal.onOk;
  closeModal();
  cb?.();
}

export function scrollBottom() {
  const v = document.getElementById('chatView');
  if (v) v.scrollTop = v.scrollHeight;
}

// ==================== 会话与消息 ====================
function pushMsg(convId: string | null, msg: Message) {
  if (!convId) return;
  set((s) => ({
    convs: s.convs.map((c) => (c.id === convId ? { ...c, messages: [...(c.messages || []), msg] } : c)),
  }));
}

function updateMsg(convId: string | null, msgId: string, patch: Partial<Message>) {
  if (!convId) return;
  set((s) => ({
    convs: s.convs.map((c) =>
      c.id === convId
        ? { ...c, messages: (c.messages || []).map((m) => (m.id === msgId ? { ...m, ...patch } : m)) }
        : c,
    ),
  }));
}

function removeMsg(convId: string | null, msgId: string) {
  if (!convId) return;
  set((s) => ({
    convs: s.convs.map((c) =>
      c.id === convId ? { ...c, messages: (c.messages || []).filter((m) => m.id !== msgId) } : c,
    ),
  }));
}

function addUserHTML(html: string) {
  const convId = get().activeId;
  pushMsg(convId, { id: nid(), role: 'user', content: { type: 'html', html } });
}

function addAI(content: MessageContent, actions = false) {
  const convId = get().activeId;
  const id = nid();
  pushMsg(convId, { id, role: 'ai', content, actions });
  return id;
}

/** 异步流程里必须写回「发起时」的会话，不能依赖当前 activeId */
function addAIIn(convId: string | null, content: MessageContent, actions = false) {
  const id = nid();
  pushMsg(convId, { id, role: 'ai', content, actions });
  return id;
}

function ensureConv(title: string, icon: string) {
  const s = get();
  if (s.activeId && s.started) return;
  const c = { id: nid(), title, icon, messages: [] as Message[] };
  set({ convs: [c, ...s.convs], activeId: c.id, pageTitle: title });
}

function beginChat(fallbackTitle?: string) {
  const s = get();
  if (!s.started) {
    set({ started: true });
    if (!s.activeId) ensureConv(fallbackTitle || '新对话', 'fa-message');
  }
}

// ==================== 任务控制（流式 / 停止 / 隔离） ====================
let activeTask: { cancel: () => void } | null = null;

function setGenerating(on: boolean) {
  set({ generating: on });
  if (!on) activeTask = null;
}

export function cancelActiveTask() {
  if (activeTask) {
    activeTask.cancel();
    activeTask = null;
    set({ generating: false });
  }
}

export function stopGenerating() {
  cancelActiveTask();
  toast('已停止生成，已输出的内容保留');
}

// ==================== 后端接线（VITE_API_MODE=api，契约 §5） ====================
export const isApiMode = API_MODE === 'api';

/** 当前导入批次（确认面板提交时用） */
let pendingBatchId: string | null = null;

interface ApiFailure {
  code: string;
  message: string;
  hint: string;
  offline: boolean;
}

/** 错误 → 可执行文案：网络/5xx 视为服务异常，其余为业务错误 */
function apiFailure(error: unknown): ApiFailure {
  if (error instanceof ApiError) {
    return { code: error.code, message: error.message, hint: error.hint, offline: error.status >= 500 };
  }
  return {
    code: 'SERVICE_UNAVAILABLE',
    message: '服务暂时不可用（网络或服务异常）',
    hint: '请确认后端已在 127.0.0.1:8010 运行后重试',
    offline: true,
  };
}

function apiReport(error: unknown): ApiFailure {
  const info = apiFailure(error);
  if (info.offline) set({ serviceOnline: false });
  // 工作台过期（72h）或服务端数据被清理：下次调用重建工作台，不静默丢错误
  if (info.code === 'WORKSPACE_EXPIRED' || info.code === 'WORKSPACE_NOT_FOUND') {
    resetWorkspace();
    return { ...info, hint: info.hint ? `${info.hint}（已重置本次工作台，重新发起即可）` : '已重置本次工作台，重新发起即可' };
  }
  return info;
}

function failText(info: ApiFailure): string {
  return info.hint ? `${info.message} · ${info.hint}` : info.message;
}

/** 服务端真实进度 → 会话里的步骤卡（结构与原型一致，steps 按事件落位） */
function liveSteps(convId: string | null, initial: string[]) {
  const id = nid();
  let steps = [...initial];
  let index = 0;
  pushMsg(convId, { id, role: 'ai', content: { type: 'steps', steps, index } });
  return {
    onStep: (nextIndex: number, label: string) => {
      const next = [...steps];
      while (next.length <= nextIndex) next.push('');
      next[nextIndex] = label || next[nextIndex] || '';
      steps = next;
      index = nextIndex;
      updateMsg(convId, id, { content: { type: 'steps', steps, index } });
    },
    finish: () => removeMsg(convId, id),
    cancel: () =>
      updateMsg(convId, id, { content: { type: 'steps', steps, index: Math.max(0, index - 1), cancelled: true } }),
  };
}

interface ApiRunHandlers {
  onStep?: (index: number, label: string, detail: string) => void;
  onToken?: (full: string) => void;
  onCancel?: () => void;
  /** 没有会话级「生成中」状态的流程（导入面板 / 合同重试） */
  silent?: boolean;
}

/** 订阅一次 run，直到终态；取消时只发 cancel，已生成内容由调用方保留 */
async function startApiRun(runId: string, handlers: ApiRunHandlers = {}): Promise<RunEventDto | null> {
  let full = '';
  if (!handlers.silent) setGenerating(true);
  activeTask = {
    cancel: () => {
      void cancelRun(runId);
      handlers.onCancel?.();
    },
  };
  try {
    return await waitRun(runId, {
      onEvent: (event) => {
        if (event.type === 'progress') {
          handlers.onStep?.(
            Number(event.data.index ?? 0),
            String(event.data.label ?? ''),
            String(event.data.detail ?? ''),
          );
        } else if (event.type === 'token') {
          full += String(event.data.text ?? '');
          handlers.onToken?.(full);
        }
      },
    });
  } finally {
    if (!handlers.silent) setGenerating(false);
  }
}

/** 在指定会话里写一条失败卡（不静默吞掉错误） */
function addApiErrorCard(convId: string | null, info: ApiFailure, canPasteText = false) {
  addAIIn(
    convId,
    { type: 'api-error', code: info.code, message: info.message, hint: info.hint, canPasteText },
    true,
  );
}

/** 服务端会话 id（本地占位会话不能当成服务端会话复用） */
const serverConvIds = new Set<string>();

/** api 模式下会话必须落在服务端（契约 §4.8） */
async function apiStartConv(title: string, icon: string): Promise<string | null> {
  const current = get().activeId;
  set({ started: true, currentView: 'chat' });
  if (current && serverConvIds.has(current)) return current;
  try {
    const ws = await ensureWorkspace();
    const id = await ensureConversation(ws, title);
    serverConvIds.add(id);
    set((s) => ({
      convs: [{ id, title, icon, messages: [] }, ...s.convs],
      activeId: id,
      pageTitle: title,
    }));
    return id;
  } catch (error) {
    const info = apiReport(error);
    toast(failText(info));
    return null;
  }
}

/** 服务端错误码 → 可执行文案（契约 §2 错误体） */
function apiErrorInfo(error: unknown, fallbackHint: string): ApiFailure {
  const info = apiReport(error);
  if (info.hint) return info;
  const hints: Record<string, string> = {
    NO_TEXT_LAYER: 'PDF 没有文字层（扫描件），请改用粘贴合同文本或上传文字版 PDF',
    UNSUPPORTED_FORMAT: '请改用 PDF / Word(.docx) / 文本文件，或直接粘贴合同全文',
    TEXT_TOO_SHORT: '请粘贴完整合同正文（含「第 N 条」结构）',
    TOO_MANY_HOUSES: '请先移除部分房源，或拆分成本次工作台的两批比较',
    NO_DRAFTS: '请按「房源名 + 租金 + 户型/通勤」的格式补充后重试',
    LLM_UNAVAILABLE: '稍后重试；本次回答未使用模型结果',
    OCR_UNSUPPORTED: '请用 PDF 文字版、Word 或直接粘贴文本',
  };
  return { ...info, hint: hints[info.code] ?? fallbackHint };
}

function streamAnswer(html: string, taskConvId: string | null = get().activeId) {
  if (!taskConvId) return;
  const id = nid();
  pushMsg(taskConvId, {
    id,
    role: 'ai',
    actions: true,
    content: { type: 'html', html: `<div class="text-[14px] text-gray-800 leading-7 answer-stream cursor-blink"></div>` },
  });
  let i = 0;
  const iv = setInterval(() => {
    if (get().activeId !== taskConvId) {
      clearInterval(iv);
      return;
    }
    i += Math.max(2, Math.round(html.length / 90));
    const partial = html.slice(0, i);
    updateMsg(taskConvId, id, {
      content: {
        type: 'html',
        html: `<div class="text-[14px] text-gray-800 leading-7 answer-stream cursor-blink">${partial}</div>`,
      },
    });
    scrollBottom();
    if (i >= html.length) {
      clearInterval(iv);
      updateMsg(taskConvId, id, {
        content: { type: 'html', html: `<div class="text-[14px] text-gray-800 leading-7 answer-stream">${html}</div>` },
      });
      setGenerating(false);
    }
  }, 28);
  activeTask = {
    cancel: () => {
      clearInterval(iv);
      const partial = html.slice(0, Math.min(i, html.length));
      // 与原型 `el.innerHTML += hint` 一致：先交给浏览器修复不完整标签，再追加提示
      const repaired = document.createElement('div');
      repaired.innerHTML = partial;
      updateMsg(taskConvId, id, {
        content: {
          type: 'html',
          html: `<div class="text-[14px] text-gray-800 leading-7 answer-stream">${repaired.innerHTML}<div class="text-[11px] text-gray-400 mt-2"><i class="fas fa-circle-stop mr-1"></i>已停止生成，可继续追问或重新生成</div></div>`,
        },
      });
    },
  };
  setGenerating(true);
}

function runSteps(steps: string[], done: () => void) {
  const taskConvId = get().activeId;
  const id = nid();
  pushMsg(taskConvId, { id, role: 'ai', content: { type: 'steps', steps, index: 0 } });
  let i = 0;
  const tick = setInterval(() => {
    if (get().activeId !== taskConvId) {
      clearInterval(tick);
      return;
    }
    i++;
    if (i >= steps.length) {
      clearInterval(tick);
      setGenerating(false);
      removeMsg(taskConvId, id);
      if (get().activeId === taskConvId) done();
    } else {
      updateMsg(taskConvId, id, { content: { type: 'steps', steps, index: i } });
    }
  }, 650);
  activeTask = {
    cancel: () => {
      clearInterval(tick);
      updateMsg(taskConvId, id, { content: { type: 'steps', steps, index: i, cancelled: true } });
    },
  };
  setGenerating(true);
}

// ==================== 视图与工作台 ====================
export function switchView(v: 'chat' | 'houses' | 'contracts') {
  set({ currentView: v });
  const s = get();
  if (v === 'chat') {
    const c = s.convs.find((c) => c.id === s.activeId);
    set({ pageTitle: c ? c.title : '新对话' });
  } else {
    set({ pageTitle: v === 'houses' ? '本次候选房源' : '本次合同' });
  }
}

export function newChat() {
  cancelActiveTask();
  set((s) => {
    s.attachments.forEach((a) => a.url && URL.revokeObjectURL(a.url));
    return { activeId: null, started: false, ctx: { houseId: null, contractId: null }, attachments: [], inputText: '' };
  });
  set({ currentView: 'chat', pageTitle: '新对话' });
}

export function openConversation(id: string) {
  if (isApiMode) {
    void apiOpenConversation(id);
    return;
  }
  const s = get();
  if (id === s.activeId && s.started) {
    switchView('chat');
    return;
  }
  cancelActiveTask();
  const c = s.convs.find((c) => c.id === id);
  if (!c) return;
  set((st) => ({
    convs: st.convs.map((x) =>
      x.id === id && x.messages === null ? { ...x, messages: buildSeed(x.seed, st.prefs) } : x,
    ),
    activeId: id,
    started: true,
    currentView: 'chat',
    pageTitle: c.title,
  }));
}

/** 切换会话先取消当前 run（契约 §2.1 隔离规则），消息从服务端拉取 */
async function apiOpenConversation(id: string) {
  const s = get();
  if (id === s.activeId && s.started) {
    switchView('chat');
    return;
  }
  cancelActiveTask();
  const target = s.convs.find((c) => c.id === id);
  if (!target) return;
  serverConvIds.add(id);
  const needsLoad = target.messages === null;
  set((st) => ({
    convs: st.convs.map((x) => (x.id === id ? { ...x, messages: x.messages ?? [] } : x)),
    activeId: id,
    started: true,
    currentView: 'chat',
    pageTitle: target.title,
  }));
  if (!needsLoad) return;
  try {
    const rows = await listMessages(id);
    set((st) => ({
      convs: st.convs.map((x) => (x.id === id ? { ...x, messages: rows.map(messageFromDto) } : x)),
    }));
  } catch (error) {
    toast(failText(apiReport(error)));
  }
}

export function renameConv(id: string) {
  const c = get().convs.find((c) => c.id === id);
  if (!c) return;
  const name = window.prompt('重命名会话', c.title);
  if (name && name.trim()) {
    set((s) => ({
      convs: s.convs.map((x) => (x.id === id ? { ...x, title: name.trim() } : x)),
      pageTitle: s.activeId === id ? name.trim() : s.pageTitle,
    }));
    toast('已重命名');
  }
}

export function renameActiveConv() {
  const id = get().activeId;
  if (id) renameConv(id);
  else toast('当前是未保存的新对话');
}

export function askDeleteConv(id: string) {
  const c = get().convs.find((c) => c.id === id);
  if (!c) return;
  askConfirm(
    '删除会话',
    `确定删除「${c.title}」吗？会话记录不可恢复；候选房源与合同仍保留在本次工作台。`,
    () => {
      if (isApiMode) {
        cancelActiveTask();
        void deleteConversation(id).catch((error) => toast(failText(apiReport(error))));
      }
      set((s) => ({ convs: s.convs.filter((x) => x.id !== id) }));
      if (get().activeId === id) newChat();
      toast('会话已删除');
    },
  );
}

// ==================== 发起问答 / 房源推荐 ====================
let lastPrompt = '';
let lastFlow: (() => void) | null = null;

export function submitInput() {
  const s = get();
  const text = s.inputText.trim();
  const atts = s.attachments;
  set({ inputText: '', attachments: [] });
  if (!text && !atts.length) return;
  if (text) route(text);
  atts.forEach((a) => (a.kind === 'image' ? imageFlow(a.file, a.url) : uploadFlow(a.file)));
}

export function route(text: string) {
  if (text.length > 150 && /甲方|乙方|租赁合同|出租人|承租人/.test(text)) {
    pastedContractFlow(text);
    return;
  }
  if (/(预算|通勤|推荐|筛选|对比|比较|帮我选)/.test(text) && /\d/.test(text)) {
    recommendFlow(text, false);
    return;
  }
  if (/房源|地铁|租金|押[一二三两]付|通勤.*分钟/.test(text) && text.length > 30) {
    pastedHousesFlow(text);
    return;
  }
  send(text);
}

export function send(text: string, skipUser = false) {
  if (isApiMode) {
    void apiSend(text, skipUser);
    return;
  }
  lastPrompt = text;
  lastFlow = null;
  beginChat(text.length > 12 ? text.slice(0, 12) + '…' : text);
  if (!skipUser) addUserHTML(textBubble(text));
  const taskConvId = get().activeId;
  const tId = addAI({ type: 'html', html: typingDotsHTML() });
  setGenerating(true);
  const to = setTimeout(() => {
    if (get().activeId !== taskConvId) return;
    removeMsg(taskConvId, tId);
    if (!get().serviceOnline) {
      addAI({ type: 'offline', failedPrompt: text }, true);
      setGenerating(false);
      return;
    }
    streamAnswer(answerFor(text, getHouse(get().ctx.houseId), getContract(get().ctx.contractId)), taskConvId);
  }, 700);
  activeTask = {
    cancel: () => {
      clearTimeout(to);
      removeMsg(taskConvId, tId);
    },
  };
}

export function regenerate() {
  const s = get();
  const conv = s.convs.find((c) => c.id === s.activeId);
  if (conv?.messages?.length) {
    const lastAi = [...conv.messages].reverse().find((m) => m.role === 'ai');
    if (lastAi) removeMsg(conv.id, lastAi.id);
  }
  if (lastFlow) {
    const f = lastFlow;
    lastFlow = null;
    f();
  } else if (lastPrompt) {
    send(lastPrompt, true);
  }
}

const ANSWER_WRAP = 'text-[14px] text-gray-800 leading-7 answer-stream';

function streamingHTML(partial: string): string {
  return `<div class="${ANSWER_WRAP} cursor-blink">${partial}</div>`;
}

/** 停止后保留已生成内容（与原型一致：先交给浏览器修复不完整标签，再追加提示） */
function stoppedHTML(partial: string): string {
  const repaired = document.createElement('div');
  repaired.innerHTML = partial;
  return `<div class="${ANSWER_WRAP}">${repaired.innerHTML}<div class="text-[11px] text-gray-400 mt-2"><i class="fas fa-circle-stop mr-1"></i>已停止生成，可继续追问或重新生成</div></div>`;
}

/** 服务端不可用时的本地占位会话：保留用户输入与 offline 卡（不静默吞掉） */
function openOfflineConv(title: string, text: string, skipUser: boolean): void {
  const localId = `local-${nid()}`;
  set((s) => ({
    started: true,
    activeId: localId,
    pageTitle: title,
    convs: [{ id: localId, title, icon: 'fa-message', messages: [] }, ...s.convs],
  }));
  if (!skipUser) addUserHTML(textBubble(text));
  addAIIn(localId, { type: 'offline', failedPrompt: text }, true);
}

/** 问答：POST /conversations/{id}/messages + SSE token（契约 §4.8） */
async function apiSend(text: string, skipUser: boolean) {
  lastPrompt = text;
  lastFlow = null;
  const title = text.length > 12 ? text.slice(0, 12) + '…' : text;
  const convId = await apiStartConv(title, 'fa-message');
  if (!convId) {
    openOfflineConv(title, text, skipUser);
    return;
  }
  if (!skipUser) addUserHTML(textBubble(text));
  const tId = addAIIn(convId, { type: 'html', html: typingDotsHTML() });
  const ctx = { ...get().ctx };
  let streamed = '';
  try {
    const ws = await ensureWorkspace();
    await putContext(ws, ctx.houseId, ctx.contractId);
    const { run_id } = await ask(convId, text, ctx);
    const terminal = await startApiRun(run_id, {
      onToken: (full) => {
        streamed = full;
        updateMsg(convId, tId, { content: { type: 'html', html: streamingHTML(full) } });
        scrollBottom();
      },
      onCancel: () => {
        updateMsg(convId, tId, { content: { type: 'html', html: stoppedHTML(streamed) } });
      },
    });
    if (!terminal) {
      updateMsg(convId, tId, { content: { type: 'html', html: stoppedHTML(streamed) } });
      toast('事件流中断，已保留已生成内容');
      return;
    }
    if (terminal.type === 'done') {
      const answer = terminal.data.result as AnswerDto;
      updateMsg(convId, tId, { content: { type: 'html', html: answerHTML(answer) }, actions: true });
      return;
    }
    if (terminal.type === 'cancelled') {
      updateMsg(convId, tId, { content: { type: 'html', html: stoppedHTML(streamed) } });
      return;
    }
    const info = apiErrorInfo(terminal.data, '稍后重试');
    removeMsg(convId, tId);
    addApiErrorCard(convId, { ...info, message: info.message || '回答失败' });
  } catch (error) {
    const info = apiReport(error);
    removeMsg(convId, tId);
    if (info.offline) addAIIn(convId, { type: 'offline', failedPrompt: text }, true);
    else addApiErrorCard(convId, info);
  }
}

function applyPrefsFromText(text: string) {
  const cur = get().prefs;
  const bMatch = text.match(/预算[^\d]{0,8}(\d{3,6})/) || text.match(/(\d{3,6})\s*(?:元)?\s*(?:以内|以下)/);
  if (bMatch) cur.budget = parseInt(bMatch[1], 10);
  const cMatch = text.match(/通勤[^\d]{0,8}(\d{1,3})\s*分钟?/) || text.match(/(\d{1,3})\s*分钟(?:以内|以下)?/);
  if (cMatch) cur.commute = parseInt(cMatch[1], 10);
  if (/独立卫浴|独卫/.test(text)) cur.needBathroom = true;
  if (/允许合租|接受合租|可以合租/.test(text)) cur.allowShared = true;
  set({ prefs: { ...cur, soft: { ...cur.soft } } });
}

/** 按当前偏好重新推荐时展示的用户气泡（原型文案，两个模式共用） */
function prefsRecapHTML(prefs: Preferences) {
  return `<div class="text-[13px] text-gray-700 bg-gray-100 rounded-2xl rounded-tr-md px-4 py-2.5"><i class="fas fa-filter mr-1.5 text-gray-400"></i>按当前偏好重新推荐：预算 ≤ ${
    prefs.budget ? fmt(prefs.budget) : '不限'
  } · 通勤 ≤ ${prefs.commute ? prefs.commute + ' 分钟' : '不限'} · ${
    prefs.needBathroom ? '必须独立卫浴' : '不限独卫'
  } · ${prefs.allowShared ? '接受合租' : '不接受合租'}</div>`;
}

export function recommendFlow(text: string | null, fromPrefs: boolean) {
  if (isApiMode) {
    void apiRecommendFlow(text, fromPrefs);
    return;
  }
  const n = comparableHouses().length;
  const pending = activeHouses().length - n;
  if (n < 3) {
    toast(`当前仅有 ${n} 套关键字段完整可比较${pending ? `，另有 ${pending} 套待完善` : ''}，至少需要 3 套完整候选`);
    openImport('batch');
    return;
  }
  if (n > 10) {
    toast(`当前 ${n} 套关键字段完整候选超出比较上限（10 套），请先移除部分房源`);
    switchView('houses');
    return;
  }
  // 从自然语言更新偏好
  if (text) {
    applyPrefsFromText(text);
  }
  lastFlow = () => recommendFlow(null, true);
  lastPrompt = '';
  beginChat('房源推荐');
  ensureConv('候选房源推荐', 'fa-building');
  const prefs = get().prefs;
  if (text && !fromPrefs) {
    addUserHTML(textBubble(text));
  } else {
    addUserHTML(prefsRecapHTML(prefs));
  }
  const taskConvId = get().activeId;
  runSteps(
    [
      `核对硬约束（预算 / 通勤 / 独卫${prefs.allowShared ? '' : ' / 合租'}）· ${n} 套候选`,
      '计算每套真实成本与信息完整度',
      '按软偏好排序并生成取舍说明',
    ],
    () => {
      if (get().activeId !== taskConvId) return;
      addAI(
        {
          type: 'recommend',
          variant: 'live',
          snapshot: {
            houses: activeHouses().map(cloneHouse),
            prefs: clonePrefs(get().prefs),
          },
        },
        true,
      );
    },
  );
}

export function setRecView(v: RecView) {
  set({ recView: v });
}

/** 推荐：POST /recommendations + SSE → 服务端三视图排序与 explanation（契约 §4.5） */
async function apiRecommendFlow(text: string | null, fromPrefs: boolean) {
  const n = comparableHouses().length;
  const pending = activeHouses().length - n;
  if (n < 3) {
    toast(`当前仅有 ${n} 套关键字段完整可比较${pending ? `，另有 ${pending} 套待完善` : ''}，至少需要 3 套完整候选`);
    openImport('batch');
    return;
  }
  if (n > 10) {
    toast(`当前 ${n} 套关键字段完整候选超出比较上限（10 套），请先移除部分房源`);
    switchView('houses');
    return;
  }
  if (text) applyPrefsFromText(text);
  lastFlow = () => void apiRecommendFlow(null, true);
  lastPrompt = '';
  const convId = await apiStartConv('候选房源推荐', 'fa-building');
  if (!convId) return;
  const prefs = get().prefs;
  if (text && !fromPrefs) addUserHTML(textBubble(text));
  else addUserHTML(prefsRecapHTML(prefs));
  const steps = liveSteps(convId, ['硬约束过滤与成本计算', '生成推荐依据、取舍与待确认']);
  try {
    const ws = await ensureWorkspace();
    const created = await startRecommendation(ws, get().recView);
    const terminal = await startApiRun(created.run_id, { onStep: steps.onStep, onCancel: steps.cancel });
    steps.finish();
    if (!terminal) {
      addApiErrorCard(convId, { code: 'RUN_STREAM_ENDED', message: '推荐事件流中断', hint: '请重新发起推荐', offline: false });
      return;
    }
    if (terminal.type === 'done') {
      addAIIn(
        convId,
        { type: 'recommend', variant: 'server', data: recommendationResult(terminal.data.result as RecommendationDto) },
        true,
      );
      return;
    }
    if (terminal.type === 'cancelled') return;
    addApiErrorCard(convId, apiErrorInfo(terminal.data, '稍后重试'));
  } catch (error) {
    steps.finish();
    const info = apiReport(error);
    if (info.offline) addAIIn(convId, { type: 'offline', failedPrompt: text ?? '按当前偏好重新推荐' }, true);
    else addApiErrorCard(convId, info);
  }
}

export function startRecommend() {
  const n = comparableHouses().length;
  const pending = activeHouses().length - n;
  if (n < 3) {
    toast(`当前仅有 ${n} 套关键字段完整可比较${pending ? `，另有 ${pending} 套待完善` : ''}，至少需要 3 套完整候选`);
    openImport('batch');
    return;
  }
  if (n > 10) {
    toast(`当前 ${n} 套关键字段完整候选超出比较上限（10 套），请先移除部分房源`);
    switchView('houses');
    return;
  }
  openPrefs();
}

// ==================== 偏好设置 ====================
export function openPrefs() {
  set({ prefsOpen: true });
}
export function closePrefs() {
  set({ prefsOpen: false });
}
export function toggleSoft(key: SoftKey) {
  const p = get().prefs;
  set({ prefs: { ...p, soft: { ...p.soft, [key]: !p.soft[key] } } });
}
export function applyPrefs(p: Preferences) {
  set({ prefs: p });
  closePrefs();
  toast('偏好已保存');
  if (isApiMode) {
    void (async () => {
      try {
        const ws = await ensureWorkspace();
        set({ prefs: await putPreferences(ws, p) });
      } catch (error) {
        toast(failText(apiReport(error)));
        return;
      }
      await apiRecommendFlow(null, true);
    })();
    return;
  }
  recommendFlow(null, true);
}

// ==================== 导入候选房源 ====================
export function openImport(tab?: ImportInputTab) {
  const t = tab || 'paste';
  set({ importModal: { open: true, tab: t, panel: t } });
}
export function closeImport() {
  set({ importModal: { open: false, tab: 'paste', panel: 'paste' }, pendingRows: [], importFail: null, pendingError: null, importProgress: null });
}
export function switchImportTab(tab: ImportTab) {
  if (tab === 'confirm') {
    set({ importModal: { open: true, tab: get().importModal.tab, panel: 'confirm' } });
    return;
  }
  set({ importModal: { open: true, tab, panel: tab } });
}
export function setImportText(kind: 'paste' | 'batch', value: string) {
  set((s) => ({ importTexts: { ...s.importTexts, [kind]: value } }));
}
export function fillDemoBatch() {
  setImportText('batch', DEMO_BATCH_TEXT);
  toast('已填入 5 套演示房源，点击「AI 批量提取」继续');
}

export function doParsePaste(text: string) {
  const t = text.trim();
  if (!t) {
    toast('请先粘贴房源描述');
    return;
  }
  if (isApiMode) {
    void apiImportFlow('paste', t, '粘贴单条');
    return;
  }
  const list = parseHousesInput(t);
  if (!list.length) {
    showImportFail('paste', '未能从文本中识别出房源信息，请补充租金、户型或通勤等关键内容后重试。');
    return;
  }
  const batchId = nextBatchId();
  list.forEach((h) => {
    h.source = 'paste' as SourceKey;
    h.batch = batchId;
  });
  showConfirm(list, '粘贴单条');
}

export function doParseBatch(text: string) {
  const t = text.trim();
  if (!t) {
    toast('请先粘贴多条房源信息');
    return;
  }
  if (isApiMode) {
    void apiImportFlow('batch', t, '批量粘贴');
    return;
  }
  const isDemo = t === DEMO_BATCH_TEXT.trim();
  const list = isDemo ? demoHouses('batch') : parseHousesInput(t);
  if (!list.length) {
    showImportFail('batch', '没有识别到有效房源条目，请检查格式（每条至少包含租金或户型信息）。');
    return;
  }
  if (!isDemo) {
    const batchId = nextBatchId();
    list.forEach((h) => {
      h.source = 'batch' as SourceKey;
      h.batch = batchId;
    });
  }
  showConfirm(list, '批量粘贴');
}

function toPendingRow(h: House): PendingRow {
  return {
    house: h,
    name: h.name || '',
    rent: h.rent == null ? '' : String(h.rent),
    deposit: h.deposit || '',
    property: h.propertyFee == null ? '' : String(h.propertyFee),
    commute: h.commuteMin == null ? '' : String(h.commuteMin),
    layout: h.layout || '',
  };
}

export function showConfirm(list: House[], sourceLabel: string) {
  set({
    pendingRows: list.map(toPendingRow),
    pendingTitle: `AI 提取结果 · 识别到 ${list.length} 套房源（来源：${sourceLabel}）`,
    pendingSource: sourceLabel,
    pendingCount: `确认后新增 ${list.length} 套 · 当前已有 ${activeHouses().length} 套（比较上限 10 套）`,
    importFail: null,
    pendingError: null,
    importModal: { open: true, tab: get().importModal.tab, panel: 'confirm' },
  });
}

export function showImportFail(backTab: ImportTab, reason: string) {
  set({
    importFail: { reason, backTab },
    importModal: { open: true, tab: get().importModal.tab, panel: 'confirm' },
  });
}

/** 导入解析进度（真实 SSE 进度，渲染在导入面板里） */
function importProgressCard(initial: string[]) {
  let steps = [...initial];
  let index = 0;
  set({ importProgress: { steps, index } });
  return {
    onStep: (nextIndex: number, label: string) => {
      const next = [...steps];
      while (next.length <= nextIndex) next.push('');
      next[nextIndex] = label || next[nextIndex] || '';
      steps = next;
      index = nextIndex;
      set({ importProgress: { steps, index } });
    },
    finish: () => set({ importProgress: null }),
    cancel: () => set({ importProgress: null }),
  };
}

/** 确认面板：用服务端 drafts（含 confidence / evidence / missing / duplicate_of） */
function showConfirmDrafts(drafts: HouseDraftDto[], sourceLabel: string, count: number) {
  const rows: PendingRow[] = drafts.map((draft) => ({
    ...toPendingRow(draftToPending(draft)),
    missing: draft.missing ?? [],
    duplicateOf: draft.duplicate_of ?? null,
    evidence: draft.evidence ?? {},
  }));
  set({
    pendingRows: rows,
    pendingTitle: `AI 提取结果 · 识别到 ${count || rows.length} 套房源（来源：${sourceLabel}）`,
    pendingSource: sourceLabel,
    pendingCount: `确认后新增 ${rows.length} 套 · 当前已有 ${activeHouses().length} 套（比较上限 10 套）`,
    importFail: null,
    pendingError: null,
    importModal: { open: true, tab: get().importModal.tab, panel: 'confirm' },
  });
}

/** 导入：POST /import-batches + SSE 进度（契约 §4.2） */
async function apiImportFlow(source: 'paste' | 'batch', text: string, sourceLabel: string, chat?: { convId: string | null }) {
  const progress = chat
    ? liveSteps(chat.convId, ['解析文档', 'AI 提取房源字段'])
    : importProgressCard(['解析文档', 'AI 提取房源字段']);
  try {
    const ws = await ensureWorkspace();
    const batch = await importText(ws, source, text);
    pendingBatchId = batch.id;
    const terminal = batch.run_id
      ? await startApiRun(batch.run_id, { silent: true, onStep: progress.onStep })
      : null;
    progress.finish();
    if (!terminal) {
      showImportFail(source, '事件流中断，请重试');
      return;
    }
    if (terminal.type === 'cancelled') {
      toast('已取消导入');
      return;
    }
    if (terminal.type === 'error') {
      showImportFail(source, failText(apiErrorInfo(terminal.data, '请换个格式重试')));
      return;
    }
    const payload = terminal.data.result as BatchDto;
    showConfirmDrafts(payload?.drafts ?? [], sourceLabel, payload?.house_count ?? 0);
  } catch (error) {
    set({ importProgress: null });
    showImportFail(source, failText(apiErrorInfo(error, '请检查文本内容后重试')));
  }
}

/** 文件页（xlsx / xls / docx / txt / csv / md）：真实 multipart 上传 + SSE 进度 */
export async function importHouseFile(file: File) {
  const progress = importProgressCard([`上传文件（${file.name}）`, '解析文档并识别房源条目', 'AI 提取字段']);
  try {
    const ws = await ensureWorkspace();
    const batch = await importFile(ws, file);
    pendingBatchId = batch.id;
    const terminal = batch.run_id
      ? await startApiRun(batch.run_id, {
          silent: true,
          onStep: (index, label) => progress.onStep(index + 1, label),
        })
      : null;
    progress.finish();
    if (!terminal) {
      showImportFail('file', '事件流中断，请重试');
      return;
    }
    if (terminal.type === 'cancelled') {
      toast('已取消导入');
      return;
    }
    if (terminal.type === 'error') {
      showImportFail('file', failText(apiErrorInfo(terminal.data, '请检查文件内容后重试')));
      return;
    }
    const payload = terminal.data.result as BatchDto;
    showConfirmDrafts(payload?.drafts ?? [], `文件导入：${file.name}`, payload?.house_count ?? 0);
  } catch (error) {
    set({ importProgress: null });
    showImportFail('file', failText(apiErrorInfo(error, '请检查文件格式与大小后重试')));
  }
}

export function updatePendingRow(index: number, patch: Partial<PendingRow>) {
  set((s) => ({
    pendingRows: s.pendingRows.map((r, i) => (i === index ? { ...r, ...patch } : r)),
  }));
}

export function slicePendingImport(limit: number) {
  const s = get();
  if (limit > 0 && s.pendingRows.length > limit) {
    showConfirm(
      s.pendingRows.slice(0, limit).map((r) => r.house),
      s.pendingSource || '导入候选房源',
    );
    toast(`已截取前 ${limit} 套，满足 10 套单次比较上限`);
  }
}

export function confirmImport() {
  if (isApiMode) {
    void apiConfirmImport();
    return;
  }
  const s = get();
  if (!s.pendingRows.length) return;
  let added = 0;
  let skipped = 0;
  const toAdd: House[] = [];
  s.pendingRows.forEach((r) => {
    const h: House = {
      ...r.house,
      name: r.name || r.house.name,
      rent: r.rent ? parseInt(r.rent, 10) : null,
      deposit: r.deposit || null,
      propertyFee: r.property ? parseInt(r.property, 10) : null,
      commuteMin: r.commute ? parseInt(r.commute, 10) : null,
      layout: r.layout || '',
    };
    const dup = activeHouses().find((x) => x.rent === h.rent && x.rent != null && x.name === h.name);
    if (dup) {
      skipped++;
      return;
    }
    toAdd.push(h);
    added++;
  });
  set((st) => ({ houses: [...st.houses, ...toAdd] }));
  closeImport();
  const curCount = activeHouses().length;
  let msg = skipped ? `已加入 ${added} 套，${skipped} 套因重复被跳过` : `已加入 ${added} 套候选房源`;
  if (curCount > 10) msg += `（当前共 ${curCount} 套，超出单次比较上限 10 套，筛选推荐前需先精简）`;
  toast(msg);
  set({ importTexts: { paste: '', batch: '' } });
}

/** 确认：POST /import-batches/{id}/confirm，把用户改过的字段写入候选（契约 §4.2） */
async function apiConfirmImport() {
  const s = get();
  if (!s.pendingRows.length) return;
  if (!pendingBatchId) {
    toast('导入批次已失效，请返回重新解析');
    return;
  }
  const houses: House[] = s.pendingRows.map((r) => ({
    ...r.house,
    name: r.name || r.house.name,
    rent: r.rent ? parseInt(r.rent, 10) : null,
    deposit: r.deposit || null,
    propertyFee: r.property ? parseInt(r.property, 10) : null,
    commuteMin: r.commute ? parseInt(r.commute, 10) : null,
    layout: r.layout || '',
  }));
  const evidence: Record<string, Record<string, string>> = {};
  s.pendingRows.forEach((r) => {
    if (r.evidence && Object.keys(r.evidence).length) evidence[r.house.id] = r.evidence;
  });
  try {
    const result = await confirmBatch(pendingBatchId, houses, evidence);
    pendingBatchId = null;
    set((st) => ({ houses: [...st.houses, ...result.houses] }));
    closeImport();
    set({ importTexts: { paste: '', batch: '' } });
    toast(result.hint ? `已加入 ${result.houses.length} 套候选房源。${result.hint}` : `已加入 ${result.houses.length} 套候选房源`);
  } catch (error) {
    const info = apiErrorInfo(error, '请减少本次导入数量或拆分批次后重试');
    set({ pendingError: failText(info) });
    toast(failText(info));
  }
}

// ==================== 候选房源操作 ====================

/** 把一次房源改动同时落到本地与后端（api 模式），以后端返回为准 */
function persistHouse(id: string, patch: Partial<Record<keyof House | 'dropReason' | 'status', unknown>>) {
  void patchHouse(id, patch)
    .then((saved) => set((s) => ({ houses: s.houses.map((h) => (h.id === id ? saved : h)) })))
    .catch((error) => toast(failText(apiReport(error))));
}

/** 上下文变化同步到工作台（api 模式） */
function persistContext(houseId: string | null, contractId: string | null) {
  void ensureWorkspace()
    .then((ws) => putContext(ws, houseId, contractId))
    .catch((error) => toast(failText(apiReport(error))));
}

export function askRemoveHouse(id: string) {
  if (!isLiveHouse(id)) {
    toast('历史演示数据仅供查看，请先导入到本次工作台');
    return;
  }
  const h = getHouse(id);
  if (!h) return;
  askConfirm('移除房源', `确定把「${h.name}」移出本次候选吗？关联的备注与看房记录会一并移除。`, () => {
    cancelActiveTask();
    const nextCtx =
      get().ctx.houseId === id ? { houseId: null, contractId: null } : { ...get().ctx };
    set((s) => ({
      houses: s.houses.filter((x) => x.id !== id),
      ctx: nextCtx,
    }));
    if (isApiMode) {
      void deleteHouseApi(id).catch((error) => toast(failText(apiReport(error))));
      persistContext(nextCtx.houseId, nextCtx.contractId);
    }
    toast('已移出候选');
  });
}

export function setTargetHouse(id: string, silent = false) {
  if (!isLiveHouse(id)) {
    toast('历史演示数据仅供查看，请先导入到本次工作台');
    return;
  }
  const h = getHouse(id);
  if (!h) return;
  const doSet = () => {
    cancelActiveTask();
    const next = { houseId: id, contractId: h.contractId || null };
    set({ ctx: next });
    if (isApiMode) persistContext(next.houseId, next.contractId);
    if (!silent) toast(`当前房源已切换为「${h.name}」，后续回答将围绕这套房`);
  };
  const cur = get().ctx.houseId;
  if (cur && cur !== id) {
    const old = getHouse(cur);
    askConfirm(
      '切换当前房源',
      `当前正在围绕「${old ? old.name : ''}」对话，确定切换为「${h.name}」吗？切换后回答不再引用原房源。`,
      doSet,
      '切换',
    );
  } else doSet();
}

export function removeCtx(kind: 'house' | 'contract') {
  cancelActiveTask();
  if (kind === 'house') {
    set({ ctx: { houseId: null, contractId: null } });
    if (isApiMode) persistContext(null, null);
    toast('已移除当前房源上下文，后续回答不再引用该房源');
  }
  if (kind === 'contract') {
    const next = { ...get().ctx, contractId: null };
    set({ ctx: next });
    if (isApiMode) persistContext(next.houseId, next.contractId);
    toast('已移除合同上下文，后续回答不再声称“根据你的合同”');
  }
}

export function dropHouse(id: string) {
  if (!isLiveHouse(id)) {
    toast('历史演示数据仅供查看，请先导入到本次工作台');
    return;
  }
  const h = getHouse(id);
  if (!h) return;
  const reason = window.prompt('标记放弃：可以简单记录原因（如“超预算”“通勤太长”）', h.dropReason || '');
  if (reason === null) return;
  const nextCtx = get().ctx.houseId === id ? { houseId: null, contractId: null } : { ...get().ctx };
  set((s) => ({
    houses: s.houses.map((x) => (x.id === id ? { ...x, status: 'dropped' as const, dropReason: reason.trim() } : x)),
    ctx: nextCtx,
    houseDrawer: { ...s.houseDrawer, open: false },
  }));
  if (isApiMode) {
    persistHouse(id, { status: 'dropped', dropReason: reason.trim() });
    persistContext(nextCtx.houseId, nextCtx.contractId);
  }
  toast('已标记放弃，不再参与比较');
}

export function restoreHouse(id: string) {
  if (!isLiveHouse(id)) {
    toast('历史演示数据仅供查看，请先导入到本次工作台');
    return;
  }
  set((s) => ({
    houses: s.houses.map((x) => (x.id === id ? { ...x, status: 'active' as const } : x)),
  }));
  if (isApiMode) persistHouse(id, { status: 'active' });
  toast('已恢复为候选房源');
}

export function openHouseDrawer(id: string, anchor?: string) {
  if (!getHouse(id)) return;
  set({ houseDrawer: { open: true, houseId: id, anchor: anchor || null } });
}

export function closeHouseDrawer() {
  set((s) => ({ houseDrawer: { ...s.houseDrawer, open: false } }));
}

export function saveNotes(houseId: string, value: string) {
  if (!isLiveHouse(houseId)) {
    toast('历史演示数据仅供查看');
    return;
  }
  set((s) => ({ houses: s.houses.map((h) => (h.id === houseId ? { ...h, notes: value.trim() } : h)) }));
  if (isApiMode) persistHouse(houseId, { notes: value.trim() });
  toast('备注已保存');
}

export function addVisit(houseId: string, text: string) {
  if (!isLiveHouse(houseId)) {
    toast('历史演示数据仅供查看');
    return;
  }
  const v = text.trim();
  if (!v) return;
  const h = getHouse(houseId);
  if (!h) return;
  const time = new Date().toISOString().slice(5, 10).replace('-', '/');
  const visits = [...h.visits, { time, text: v }];
  set((s) => ({ houses: s.houses.map((x) => (x.id === houseId ? { ...x, visits } : x)) }));
  if (isApiMode) persistHouse(houseId, { visits });
  toast('已添加看房记录');
}

export function addTodo(houseId: string, text: string) {
  if (!isLiveHouse(houseId)) {
    toast('历史演示数据仅供查看');
    return;
  }
  const v = text.trim();
  if (!v) return;
  const h = getHouse(houseId);
  if (!h) return;
  const todos = [...h.todos, v];
  set((s) => ({ houses: s.houses.map((x) => (x.id === houseId ? { ...x, todos } : x)) }));
  if (isApiMode) persistHouse(houseId, { todos });
  toast('已添加待确认问题');
}

// ==================== 合同与核验 ====================
export function openContract(clauseId: number | null, contractId: string | null) {
  const s = get();
  const target =
    (contractId ? getContract(contractId) : null) ||
    (s.ctx.contractId ? getContract(s.ctx.contractId) : null) ||
    s.contracts.find((c) => c.status === 'done');
  if (!target) {
    toast('暂无已解析的合同');
    return;
  }
  set({ contractDrawer: { open: true, contractId: target.id, clauseId: clauseId ?? null } });
}

export function closeContract() {
  set((s) => ({ contractDrawer: { ...s.contractDrawer, open: false } }));
}

export function copyScript(contractId: string) {
  const c = getContract(contractId);
  navigator.clipboard?.writeText(c?.negotiation || '');
  toast('谈判话术已复制到剪贴板');
}

export function askDeleteContract(id: string) {
  const c = getContract(id);
  if (!c) return;
  askConfirm('删除合同', `确定删除「${c.name}」吗？关联的核验结果会一并删除。`, () => {
    const unbind = (h: House) => (h.contractId === id ? { ...h, contractId: null } : h);
    set((s) => ({
      contracts: s.contracts.filter((x) => x.id !== id),
      houses: s.houses.map(unbind),
      ctx: s.ctx.contractId === id ? { ...s.ctx, contractId: null } : s.ctx,
    }));
    if (isApiMode) {
      void deleteContractApi(id).catch((error) => toast(failText(apiReport(error))));
      const next = get().ctx;
      persistContext(next.houseId, next.contractId);
    }
    toast('合同已删除');
  });
}

export function retryFailedContract(id: string) {
  if (isApiMode) {
    void apiRetryContract(id);
    return;
  }
  set((s) => ({ contracts: s.contracts.filter((x) => x.id !== id) }));
  pastedContractFlow(DEMO_CONTRACT_TEXT);
}

/** 重新解析：POST /contracts/{id}/retry + SSE（契约 §4.6） */
async function apiRetryContract(id: string) {
  try {
    const created = await retryContract(id);
    const terminal = await startApiRun(created.run_id, { silent: true });
    if (terminal?.type === 'done') {
      const contract = contractFromDto(terminal.data.result as ContractDto);
      set((s) => ({ contracts: s.contracts.map((c) => (c.id === id ? contract : c)) }));
      toast('合同已重新解析');
      return;
    }
    const info = apiErrorInfo(terminal?.data ?? new Error('retry'), '可再次点「重新解析」重试');
    toast(failText(info));
  } catch (error) {
    toast(failText(apiReport(error)));
  }
}

export function showVerificationCard(houseId: string) {
  if (isApiMode) {
    void apiVerify(houseId);
    return;
  }
  if (!isLiveHouse(houseId)) {
    toast('历史演示数据仅供查看，请先导入到本次工作台');
    return;
  }
  const h = getHouse(houseId);
  const c = h && h.contractId ? getContract(h.contractId) : null;
  if (!h || !c) {
    toast('该房源尚未绑定合同');
    return;
  }
  switchView('chat');
  beginChat(h.name + ' 合同核验');
  ensureConv(h.name + ' 合同核验', 'fa-file-contract');
  set({ ctx: { houseId: h.id, contractId: c.id } });
  addAI({ type: 'verify', houseId: h.id, contractId: c.id }, true);
}

export function openBindEntry() {
  const s = get();
  if (s.ctx.houseId) {
    bindContractEntry(s.ctx.houseId);
    return;
  }
  if (activeHouses().length) {
    switchView('houses');
    toast('请先在目标房源上点击「绑定合同」');
  } else {
    toast('请先导入候选房源并设定目标房源');
    openImport('batch');
  }
}

export function bindContractEntry(houseId: string) {
  if (!isLiveHouse(houseId)) {
    toast('历史演示数据仅供查看，请先导入到本次工作台');
    return;
  }
  const h = getHouse(houseId);
  if (!h) return;
  if (h.contractId) {
    showVerificationCard(houseId);
    return;
  }
  if (isApiMode) {
    void apiBindEntry(houseId);
    return;
  }
  cancelActiveTask();
  if (get().ctx.houseId !== houseId) setTargetHouse(houseId, true);
  switchView('chat');
  beginChat(h.name + ' 合同核验');
  ensureConv(h.name + ' 合同核验', 'fa-file-contract');
  lastFlow = () => bindContractEntry(houseId);
  lastPrompt = '';
  addAI({ type: 'bind-options', houseId }, true);
}

function finishBindContract(c: Contract) {
  set((s) => ({ contracts: [c, ...s.contracts] }));
  const h = c.boundHouseId ? getHouse(c.boundHouseId) : null;
  if (h) {
    set((s) => ({ houses: s.houses.map((x) => (x.id === h.id ? { ...x, contractId: c.id } : x)) }));
  }
  set((s) => ({ ctx: { ...s.ctx, contractId: c.id } }));
  const taskConvId = get().activeId;
  runSteps(
    ['解析合同（7 项关键条款）', '抽取当事人 / 金额 / 日期', `与房源 ${h ? h.no : ''} 的承诺逐项核验`],
    () => {
      if (get().activeId !== taskConvId) return;
      if (h) addAI({ type: 'verify', houseId: h.id, contractId: c.id }, true);
      else
        addAI(
          { type: 'html', html: `<div class="text-[14px] text-gray-800 leading-7">合同已加入「本次合同」。设定目标房源后可进行逐项核验。</div>` },
          true,
        );
    },
  );
}

export function pastedContractFlow(text: string) {
  if (isApiMode) {
    void apiPastedContract(text);
    return;
  }
  lastFlow = null;
  lastPrompt = text;
  beginChat('粘贴合同核验');
  const cur = getHouse(get().ctx.houseId);
  ensureConv((get().ctx.houseId ? (cur?.name || '') + ' ' : '') + '合同核验', 'fa-file-contract');
  addUserHTML(`<div class="bg-gray-100 rounded-2xl rounded-tr-md px-4 py-3 text-[13px] text-gray-700 leading-relaxed">
        <div class="text-[11px] text-gray-400 mb-1.5"><i class="fas fa-paste mr-1"></i>粘贴的合同文本（约 ${text.length} 字）</div>
        ${esc(text.slice(0, 120))}<span class="text-gray-400">…</span></div>`);
  if (text.length < 200) {
    addAI({ type: 'contract-too-short' }, true);
    set((s) => ({
      contracts: [
        mkContract({ name: '粘贴的合同文本（过短）', source: '粘贴文本', status: 'failed', reason: '文本过短，未识别为有效合同' }),
        ...s.contracts,
      ],
    }));
    return;
  }
  const c = buildBoundContract('粘贴的合同文本', '粘贴文本', text.length + ' 字', get().ctx.houseId);
  finishBindContract(c);
}

// ==================== 合同接入后端（api 模式） ====================

/** 把核验后才会绑定的房源 ↔ 合同关系先落到本地（服务端由核验接口建立） */
function bindHouseContract(houseId: string, contractId: string) {
  set((s) => ({ houses: s.houses.map((h) => (h.id === houseId ? { ...h, contractId } : h)) }));
}

/** 解析失败的合同也要进「本次合同」，否则用户无法重新解析（不制造假数据，拉不到就不展示） */
async function trackFailedContract(contractId: string) {
  try {
    const contract = contractFromDto(await fetchContract(contractId));
    set((s) => (s.contracts.some((c) => c.id === contract.id) ? s : { contracts: [contract, ...s.contracts] }));
  } catch {
    /* 合同详情拉不到时保持列表不变 */
  }
}

/** 解析完成：入列表 → 绑定 → 直接退核验（与原型 finishBindContract 一致） */
async function finishApiContract(convId: string | null, contract: Contract) {
  set((s) => ({ contracts: [contract, ...s.contracts], ctx: { ...s.ctx, contractId: contract.id } }));
  const houseId = contract.boundHouseId;
  if (!houseId) {
    addAIIn(
      convId,
      {
        type: 'html',
        html: `<div class="text-[14px] text-gray-800 leading-7">合同已加入「本次合同」。设定目标房源后可进行逐项核验。</div>`,
      },
      true,
    );
    toast('合同已解析并加入本次合同');
    return;
  }
  bindHouseContract(houseId, contract.id);
  cancelActiveTask();
  await apiVerify(houseId, contract.id);
}

/** 粘贴合同：POST /contracts + SSE（parse→extract→rules）（契约 §4.6） */
async function apiPastedContract(text: string) {
  lastPrompt = text;
  const houseId = get().ctx.houseId;
  const cur = getHouse(houseId);
  const convId = await apiStartConv((houseId ? (cur?.name || '') + ' ' : '') + '合同核验', 'fa-file-contract');
  if (!convId) return;
  lastFlow = () => void apiPastedContract(text);
  addUserHTML(`<div class="bg-gray-100 rounded-2xl rounded-tr-md px-4 py-3 text-[13px] text-gray-700 leading-relaxed">
        <div class="text-[11px] text-gray-400 mb-1.5"><i class="fas fa-paste mr-1"></i>粘贴的合同文本（约 ${text.length} 字）</div>
        ${esc(text.slice(0, 120))}<span class="text-gray-400">…</span></div>`);
  const steps = liveSteps(convId, ['解析文档', '抽取条款（含原文定位）', '匹配风险规则库']);
  try {
    const ws = await ensureWorkspace();
    const created = await saveContract(ws, text, houseId);
    const terminal = await startApiRun(created.run_id, { onStep: steps.onStep, onCancel: steps.cancel });
    steps.finish();
    if (!terminal) {
      addApiErrorCard(convId, { code: 'RUN_STREAM_ENDED', message: '合同解析事件流中断', hint: '可重新粘贴合同重试', offline: false });
      return;
    }
    if (terminal.type === 'cancelled') {
      toast('已停止生成，已输出的内容保留');
      return;
    }
    if (terminal.type === 'done') {
      await finishApiContract(convId, contractFromDto(terminal.data.result as ContractDto));
      return;
    }
    const info = apiErrorInfo(terminal.data, '请粘贴完整合同正文后重试');
    if (info.code === 'TEXT_TOO_SHORT' || info.code === 'NO_CLAUSES') addAIIn(convId, { type: 'contract-too-short' }, true);
    else addApiErrorCard(convId, info, info.code === 'NO_TEXT_LAYER');
    await trackFailedContract(created.contract_id);
  } catch (error) {
    steps.finish();
    const info = apiErrorInfo(error, '请粘贴完整合同正文后重试');
    if (info.code === 'TEXT_TOO_SHORT') addAIIn(convId, { type: 'contract-too-short' }, true);
    else if (info.offline) addAIIn(convId, { type: 'offline', failedPrompt: text.slice(0, 40) }, true);
    else addApiErrorCard(convId, info, info.code === 'NO_TEXT_LAYER');
  }
}

/** 上传合同文件：multipart + SSE（契约 §4.6），失败按错误码给可执行文案 */
async function apiUploadContract(file: File) {
  const convId = await apiStartConv(file.name.replace(/\.[^.]+$/, '') + ' 核验', 'fa-file-contract');
  if (!convId) return;
  const houseId = get().ctx.houseId;
  const size = fmtSize(file.size);
  const isPdf = /\.pdf$/i.test(file.name);
  const cardId = nid();
  lastFlow = () => void apiUploadContract(file);
  lastPrompt = '';
  let percent = 5;
  const card = (statusHtml: string, redBar = false) => ({
    type: 'html' as const,
    html: uploadCardHTML(file.name, size, isPdf, percent, statusHtml, redBar),
  });
  pushMsg(convId, { id: cardId, role: 'user', content: card('上传中…') });
  try {
    const ws = await ensureWorkspace();
    const created = await uploadContract(ws, file, houseId);
    percent = 30;
    updateMsg(convId, cardId, { content: card('解析中…') });
    const terminal = await startApiRun(created.run_id, {
      onStep: (_index, label) => {
        percent = Math.min(95, percent + 20);
        updateMsg(convId, cardId, { content: card(label || '解析中…') });
      },
      onCancel: () => updateMsg(convId, cardId, { content: card('已取消解析') }),
    });
    if (!terminal) {
      addApiErrorCard(convId, { code: 'RUN_STREAM_ENDED', message: '合同解析事件流中断', hint: '可重新上传文件后重试', offline: false });
      return;
    }
    if (terminal.type === 'cancelled') {
      toast('已停止生成，已输出的内容保留');
      return;
    }
    if (terminal.type === 'done') {
      percent = 100;
      updateMsg(convId, cardId, {
        content: card(`${size} · <span class="text-green-600"><i class="fas fa-check mr-0.5"></i>已加入当前对话</span>`),
      });
      await finishApiContract(convId, contractFromDto(terminal.data.result as ContractDto));
      return;
    }
    percent = 100;
    const info = apiErrorInfo(terminal.data, '请检查文件后重试');
    updateMsg(convId, cardId, { content: card(`${size} · <span class="text-red-500">解析失败</span>`, true) });
    if (info.code === 'TEXT_TOO_SHORT' || info.code === 'NO_CLAUSES') addAIIn(convId, { type: 'contract-too-short' }, true);
    else addApiErrorCard(convId, info, info.code === 'NO_TEXT_LAYER' || info.code === 'UNSUPPORTED_FORMAT' || info.code === 'OCR_UNSUPPORTED');
    await trackFailedContract(created.contract_id);
  } catch (error) {
    percent = 100;
    const info = apiErrorInfo(error, '请检查文件格式与大小后重试');
    updateMsg(convId, cardId, {
      content: card(`${size} · <span class="text-red-500">${esc(info.message)}</span>`, true),
    });
    if (info.offline) addAIIn(convId, { type: 'offline', failedPrompt: file.name }, true);
    else addApiErrorCard(convId, info, info.code === 'NO_TEXT_LAYER' || info.code === 'UNSUPPORTED_FORMAT' || info.code === 'OCR_UNSUPPORTED');
  }
}

/** 核验：POST /verifications + SSE → VerifyCard 用服务端 rows（契约 §4.7） */
async function apiVerify(houseId: string, contractId?: string) {
  const h = getHouse(houseId);
  const c = getContract(contractId ?? h?.contractId ?? null);
  if (!h || !c) {
    toast('该房源尚未绑定合同');
    return;
  }
  switchView('chat');
  cancelActiveTask();
  const convId = await apiStartConv(h.name + ' 合同核验', 'fa-file-contract');
  if (!convId) return;
  const next = { houseId: h.id, contractId: c.id };
  set({ ctx: next });
  persistContext(next.houseId, next.contractId);
  const steps = liveSteps(convId, ['读取房源承诺与合同条款', '逐项比对（规则 + 语义判断）']);
  try {
    const ws = await ensureWorkspace();
    const created = await startVerification(ws, h.id, c.id);
    const terminal = await startApiRun(created.run_id, { onStep: steps.onStep, onCancel: steps.cancel });
    steps.finish();
    if (!terminal) {
      addApiErrorCard(convId, { code: 'RUN_STREAM_ENDED', message: '核验事件流中断', hint: '请重新发起核验', offline: false });
      return;
    }
    if (terminal.type === 'cancelled') {
      toast('已停止生成，已输出的内容保留');
      return;
    }
    if (terminal.type === 'done') {
      bindHouseContract(h.id, c.id);
      addAIIn(
        convId,
        {
          type: 'verify',
          houseId: h.id,
          contractId: c.id,
          data: verificationResult(terminal.data.result as VerificationDto),
        },
        true,
      );
      return;
    }
    addApiErrorCard(convId, apiErrorInfo(terminal.data, '稍后重试'));
  } catch (error) {
    steps.finish();
    const info = apiReport(error);
    if (info.offline) addAIIn(convId, { type: 'offline', failedPrompt: `${h.name} 合同核验` }, true);
    else addApiErrorCard(convId, info);
  }
}

/** 绑定合同入口：服务端会话 + 绑定卡（原型结构不变） */
async function apiBindEntry(houseId: string) {
  cancelActiveTask();
  if (get().ctx.houseId !== houseId) setTargetHouse(houseId, true);
  const h = getHouse(houseId);
  if (!h) return;
  const convId = await apiStartConv(h.name + ' 合同核验', 'fa-file-contract');
  if (!convId) return;
  lastFlow = () => bindContractEntry(houseId);
  lastPrompt = '';
  addAIIn(convId, { type: 'bind-options', houseId }, true);
}

// ==================== 合同上传 / 图片附件 ====================
export function triggerFilePick() {
  document.getElementById('fileInput')?.click();
}

function uploadFlow(file: File) {
  if (isApiMode) {
    void apiUploadContract(file);
    return;
  }
  const isPdf = /\.pdf$/i.test(file.name);
  const size = fmtSize(file.size);
  beginChat(file.name.replace(/\.[^.]+$/, '') + ' 核验');
  ensureConv(file.name.replace(/\.[^.]+$/, ''), 'fa-file-contract');
  const taskConvId = get().activeId;
  const id = nid();
  pushMsg(taskConvId, {
    id,
    role: 'user',
    content: { type: 'html', html: uploadCardHTML(file.name, size, isPdf, 5, '上传中…', false) },
  });
  let p = 5;
  setGenerating(true);
  const iv = setInterval(() => {
    if (get().activeId !== taskConvId) {
      clearInterval(iv);
      return;
    }
    p = Math.min(100, p + Math.random() * 22);
    const done = p >= 100;
    const status = done
      ? isPdf
        ? `${size} · <span class="text-green-600"><i class="fas fa-check mr-0.5"></i>已加入当前对话</span>`
        : `${size} · <span class="text-red-500">格式暂不支持</span>`
      : '上传中…';
    updateMsg(taskConvId, id, { content: { type: 'html', html: uploadCardHTML(file.name, size, isPdf, p, status, done && !isPdf) } });
    if (done) {
      clearInterval(iv);
      setGenerating(false);
      if (isPdf) {
        const c = buildBoundContract(file.name, '上传', size, get().ctx.houseId);
        finishBindContract(c);
      } else {
        addAI({ type: 'upload-unsupported' }, true);
        set((s) => ({
          contracts: [mkContract({ name: file.name, source: '上传', status: 'failed', reason: '格式暂不支持' }), ...s.contracts],
        }));
      }
    }
  }, 160);
  activeTask = {
    cancel: () => {
      clearInterval(iv);
      updateMsg(taskConvId, id, { content: { type: 'html', html: uploadCardHTML(file.name, size, isPdf, p, '已取消上传', false) } });
    },
  };
}

function imageBubbleHTML(url: string, name: string, size: string) {
  return `<div class="bg-white border border-gray-200 rounded-2xl rounded-tr-md p-2.5 shadow-sm w-[240px]">
          <img src="${url}" class="w-full h-32 object-cover rounded-xl border border-gray-100" alt="粘贴的图片">
          <div class="flex items-center gap-1.5 mt-2 px-1 text-[11px] text-gray-500">
            <i class="fas fa-image text-gray-400"></i><span class="truncate">${esc(name || '粘贴的图片')}</span><span class="shrink-0">· ${size}</span>
          </div>
        </div>`;
}

const IMAGE_OCR_HTML = `<p class="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5"><i class="fas fa-circle-info text-brand-600"></i> 图片已收到</p>
          <b>图片内容识别（OCR）是规划能力</b>，我暂时读不了图里的文字。<br><br>
          如果是合同照片 / 截图，建议：① 导出为 <b>PDF</b> 上传；② 或直接<b>粘贴合同文字</b>。`;

function imageFlow(file: File, url: string | null) {
  const size = fmtSize(file.size);
  const u = url || URL.createObjectURL(file);
  if (isApiMode) {
    void (async () => {
      const convId = await apiStartConv('图片附件咨询', 'fa-image');
      if (!convId) return;
      addUserHTML(imageBubbleHTML(u, file.name, size));
      addAIIn(convId, { type: 'html', html: `<div class="${ANSWER_WRAP}">${IMAGE_OCR_HTML}</div>` }, true);
    })();
    return;
  }
  beginChat('图片附件咨询');
  ensureConv('图片附件咨询', 'fa-image');
  const taskConvId = get().activeId;
  addUserHTML(imageBubbleHTML(u, file.name, size));
  const tId = addAI({ type: 'html', html: typingDotsHTML() });
  setGenerating(true);
  const to = setTimeout(() => {
    if (get().activeId !== taskConvId) return;
    removeMsg(taskConvId, tId);
    streamAnswer(IMAGE_OCR_HTML, taskConvId);
  }, 600);
  activeTask = {
    cancel: () => {
      clearTimeout(to);
      removeMsg(taskConvId, tId);
    },
  };
}

// ==================== 粘贴房源（输入框直贴） ====================
export function pastedHousesFlow(text: string) {
  if (isApiMode) {
    void apiPastedHousesFlow(text);
    return;
  }
  beginChat('房源整理');
  ensureConv('房源整理', 'fa-building');
  addUserHTML(`<div class="bg-gray-100 rounded-2xl rounded-tr-md px-4 py-3 text-[13px] text-gray-700 leading-relaxed">
        <div class="text-[11px] text-gray-400 mb-1.5"><i class="fas fa-paste mr-1"></i>粘贴的房源信息</div>${esc(text.slice(0, 140))}${
          text.length > 140 ? '<span class="text-gray-400">…</span>' : ''
        }</div>`);
  const isDemo = text.trim() === DEMO_BATCH_TEXT.trim();
  const list = isDemo ? demoHouses('batch') : parseHousesInput(text);
  if (!list.length) {
    addAI(
      {
        type: 'html',
        html: `<div class="text-[14px] text-gray-800 leading-7">没有识别到有效房源条目。每条至少包含租金或户型信息，也可以点击左下角「导入房源」用批量粘贴或文件导入。</div>`,
      },
      true,
    );
    return;
  }
  if (!isDemo) {
    const batchId = nextBatchId();
    list.forEach((h) => {
      h.source = 'batch' as SourceKey;
      h.batch = batchId;
    });
  }
  showConfirm(list, '对话粘贴');
  toast('请先确认 AI 提取的字段，确认后加入候选');
}

/** 对话里直贴房源文本 → 真实导入 + 确认面板（api 模式） */
async function apiPastedHousesFlow(text: string) {
  const convId = await apiStartConv('房源整理', 'fa-building');
  if (!convId) return;
  addUserHTML(
    `<div class="bg-gray-100 rounded-2xl rounded-tr-md px-4 py-3 text-[13px] text-gray-700 leading-relaxed">
        <div class="text-[11px] text-gray-400 mb-1.5"><i class="fas fa-paste mr-1"></i>粘贴的房源信息</div>${esc(
          text.slice(0, 140),
        )}${text.length > 140 ? '<span class="text-gray-400">…</span>' : ''}</div>`,
  );
  await apiImportFlow('batch', text.trim(), '对话粘贴', { convId });
}

// ==================== 附件暂存 ====================
export function addPendingAttachment(file: File) {
  const kind: Attachment['kind'] = file.type.startsWith('image/') ? 'image' : 'file';
  set((s) => ({
    attachments: [...s.attachments, { id: nid(), file, kind, url: kind === 'image' ? URL.createObjectURL(file) : null }],
  }));
}

export function removePendingAttachment(id: string) {
  set((s) => {
    const a = s.attachments.find((x) => x.id === id);
    if (a && a.url) URL.revokeObjectURL(a.url);
    return { attachments: s.attachments.filter((x) => x.id !== id) };
  });
}

// ==================== 服务状态（健康检查 / 重连） ====================
export function toggleService() {
  if (isApiMode) {
    void recheckService();
    return;
  }
  const online = !get().serviceOnline;
  set({ serviceOnline: online });
  toast(online ? '服务已恢复（演示）' : '已切换为服务异常状态，发送消息将看到失败与重试');
}

/** 重新探测 GET /healthz（api 模式）；恢复后补齐工作台数据 */
async function recheckService(): Promise<boolean> {
  try {
    await ping();
  } catch (error) {
    apiReport(error);
    toast('服务仍不可用，请确认后端已启动（127.0.0.1:8010）');
    return false;
  }
  const wasOffline = !get().serviceOnline;
  set({ serviceOnline: true });
  if (wasOffline) {
    try {
      const ws = await ensureWorkspace();
      const [houses, contracts] = await Promise.all([listHouses(ws, 'all'), listContracts(ws)]);
      set({ houses, contracts: contracts.map(contractFromDto) });
    } catch (error) {
      toast(failText(apiReport(error)));
    }
  }
  return true;
}

/** offline 卡片的「恢复服务并重试」：先真实探测，成功才重发 */
export function retryAfterOffline(prompt: string) {
  if (!isApiMode) {
    toggleService();
    send(prompt, true);
    return;
  }
  void (async () => {
    if (await recheckService()) send(prompt, true);
  })();
}

// ==================== 启动初始化（api 模式：工作台/房源/合同/会话都来自服务端） ====================
let booted = false;

async function loadWorkspaceState(fresh: boolean) {
  const ws = await ensureWorkspace();
  if (fresh) await putPreferences(ws, get().prefs);
  else set({ prefs: await getPreferences(ws) });
  const [houses, contracts, convs] = await Promise.all([
    listHouses(ws, 'all'),
    listContracts(ws),
    listConversations(ws),
  ]);
  set({
    serviceOnline: true,
    houses,
    contracts: contracts.map(contractFromDto),
    convs: convs.map((c) => ({ id: c.id, title: c.title, icon: 'fa-message', messages: null })),
  });
  convs.forEach((c) => serverConvIds.add(c.id));
}

async function loadWorkspaceStateWithRecovery() {
  const fresh = !sessionStorage.getItem('rg-workspace');
  try {
    await loadWorkspaceState(fresh);
  } catch (error) {
    const gone =
      error instanceof ApiError && (error.code === 'WORKSPACE_EXPIRED' || error.code === 'WORKSPACE_NOT_FOUND');
    if (!gone) throw error;
    resetWorkspace();
    toast('上一次的工作台已过期，已新建本次工作台');
    await loadWorkspaceState(true);
  }
}

export async function bootstrap() {
  if (!isApiMode || booted) return;
  booted = true;
  try {
    await ping();
    await loadWorkspaceStateWithRecovery();
  } catch (error) {
    toast(failText(apiReport(error)));
  }
}
