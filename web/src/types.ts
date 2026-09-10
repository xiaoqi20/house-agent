/** 一期原型数据模型（与《原型完善执行文档 v1.1》第 7 节字段组对应） */

import type { AnswerDto, ExplanationDto, RankItemDto, VerificationItemDto } from './api/types';

export type View = 'chat' | 'houses' | 'contracts';

export type SourceKey =
  | 'paste'
  | 'manual'
  | 'batch'
  | 'file-xlsx'
  | 'file-docx'
  | 'file-txt'
  | 'link';

export interface Visit {
  time: string;
  text: string;
}

export interface House {
  id: string;
  no: string;
  batch: string | null;
  status: 'active' | 'dropped';
  dropReason: string;
  source: SourceKey;
  raw: string;
  name: string;
  region: string;
  address: string;
  rent: number | null;
  deposit: string | null;
  agencyFee: number | null;
  propertyFee: number | null;
  propertyBear: string;
  netFee: number | null;
  otherFee: string | number | null;
  area: number | null;
  layout: string;
  floor: string;
  orientation: string;
  bathroom: boolean | null;
  lighting: string;
  furniture: string;
  commuteMin: number | null;
  commuteMode: string;
  metro: string;
  nearby: string;
  pet: string;
  shared: boolean;
  sublet: string;
  maxPeople: number | null;
  leaseReq: string;
  available: string;
  notes: string;
  visits: Visit[];
  todos: string[];
  verify: string[];
  contractId: string | null;
  linkUrl: string;
}

export type ContractStatus = 'done' | 'failed';

export interface Contract {
  id: string;
  no: string;
  name: string;
  source: string;
  time: string;
  status: ContractStatus;
  reason: string;
  size: string;
  boundHouseId: string | null;
  /** [条号, 标题, 原文] */
  clausesList: Array<[number, string, string]>;
  riskClauses: number[];
  negotiation: string;
  isDemoParse?: boolean;
}

export interface Preferences {
  budget: number | null;
  commute: number | null;
  needBathroom: boolean;
  allowShared: boolean;
  soft: {
    south: boolean;
    light: boolean;
    highFloor: boolean;
    bigArea: boolean;
    flexPay: boolean;
  };
}

export type SoftKey = keyof Preferences['soft'];

export type RecView = 'mix' | 'budget' | 'commute';

export interface DemoStore {
  houses: House[];
  contracts: Contract[];
  targetHouse: House;
  targetContract: Contract;
}

/** 推荐结果（服务端三视图排序 + explanation，前端只渲染不再本地打分） */
export interface RecommendationResult {
  id: string;
  view: RecView;
  prefsVersion: number;
  houses: House[];
  views: Record<RecView, { order: string[]; items: Record<string, RankItemDto> }>;
  explanation: Record<string, ExplanationDto>;
  about: {
    hardRules: string[];
    softRules: string[];
    window: { count: number; ok: boolean; message: string } | null;
    missing: string[];
  };
}

/** 核验结果（服务端 rows + negotiation） */
export interface VerificationResult {
  id: string;
  houseId: string;
  contractId: string;
  items: VerificationItemDto[];
  summary: Record<string, unknown>;
  negotiation: string;
}

/** 消息正文：结构化描述，由 React 组件渲染 */
export interface RecommendSnapshot {
  houses: House[];
  prefs: Preferences;
}

export type MessageContent =
  | { type: 'html'; html: string; cursor?: boolean; stopped?: boolean }
  | { type: 'steps'; steps: string[]; index: number; cancelled?: boolean }
  | { type: 'recommend'; variant: 'live'; snapshot: RecommendSnapshot }
  | { type: 'recommend'; variant: 'demo'; demoPrefs: Preferences }
  | { type: 'recommend'; variant: 'server'; data: RecommendationResult }
  | { type: 'verify'; houseId: string; contractId: string; readOnly?: boolean; data?: VerificationResult }
  | { type: 'bind-options'; houseId: string }
  | { type: 'offline'; failedPrompt: string }
  | { type: 'contract-too-short' }
  | { type: 'upload-unsupported' }
  | { type: 'api-error'; code: string; message: string; hint: string; canPasteText?: boolean };

export interface Message {
  id: string;
  role: 'user' | 'ai';
  content: MessageContent;
  actions?: boolean;
}

export type ConversationSeed = 'rec' | 'verify';

export interface Conversation {
  id: string;
  title: string;
  icon: string;
  seed?: ConversationSeed;
  messages: Message[] | null;
}

export interface Attachment {
  id: string;
  file: File;
  kind: 'image' | 'file';
  url: string | null;
}

export type ImportTab = 'paste' | 'manual' | 'batch' | 'file' | 'confirm';
export type ImportInputTab = Exclude<ImportTab, 'confirm'>;

/** 导入解析进度（api 模式的真实 SSE 进度；demo 模式用于文件页） */
export interface ImportProgress {
  steps: string[];
  index: number;
}

export interface ImportModalState {
  open: boolean;
  /** 顶部高亮的输入方式页签 */
  tab: ImportInputTab;
  /** 当前显示的正文面板（confirm = AI 字段确认） */
  panel: ImportTab;
}

/** 字段确认卡片中的可编辑值（确认时才解析为数值，与原型读取输入框一致） */
export interface PendingRow {
  house: House;
  name: string;
  rent: string;
  deposit: string;
  property: string;
  commute: string;
  layout: string;
  /** 服务端提取结果带出的缺失字段中文名（api 模式） */
  missing?: string[];
  /** 与已有候选疑似重复的房源 id（api 模式） */
  duplicateOf?: string | null;
  /** 每个字段的原文依据片段（api 模式） */
  evidence?: Record<string, string>;
}

export interface ConfirmModalState {
  open: boolean;
  title: string;
  desc: string;
  okText: string;
  onOk: (() => void) | null;
}

export interface ToastState {
  msg: string;
  key: number;
}

export interface HouseDrawerState {
  open: boolean;
  houseId: string | null;
  anchor: string | null;
}

export interface ContractDrawerState {
  open: boolean;
  contractId: string | null;
  clauseId: number | null;
}
