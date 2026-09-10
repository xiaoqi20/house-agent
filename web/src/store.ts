import { create } from 'zustand';
import type {
  Attachment,
  ConfirmModalState,
  Contract,
  ContractDrawerState,
  Conversation,
  House,
  HouseDrawerState,
  ImportModalState,
  ImportProgress,
  ImportTab,
  PendingRow,
  Preferences,
  RecView,
  ToastState,
  View,
} from './types';
import { nid } from './lib/utils';
import { API_MODE } from './api/config';

export interface AppState {
  // 视图与标题
  currentView: View;
  pageTitle: string;
  // 业务数据（本次工作台临时数据）
  houses: House[];
  contracts: Contract[];
  convs: Conversation[];
  activeId: string | null;
  started: boolean;
  prefs: Preferences;
  ctx: { houseId: string | null; contractId: string | null };
  recView: RecView;
  serviceOnline: boolean;
  hf: { q: string; filter: string; sort: string };
  // 交互状态
  generating: boolean;
  inputText: string;
  attachments: Attachment[];
  toast: ToastState | null;
  confirmModal: ConfirmModalState;
  houseDrawer: HouseDrawerState;
  contractDrawer: ContractDrawerState;
  prefsOpen: boolean;
  importModal: ImportModalState;
  importProgress: ImportProgress | null;
  pendingRows: PendingRow[];
  pendingTitle: string;
  pendingCount: string;
  pendingSource: string;
  pendingError: string | null;
  importFail: { reason: string; backTab: ImportTab } | null;
  importTexts: { paste: string; batch: string };
}

export const initialPrefs: Preferences = {
  budget: 6000,
  commute: 45,
  needBathroom: true,
  allowShared: false,
  soft: { south: false, light: false, highFloor: false, bigArea: false, flexPay: false },
};

/** demo 模式预置的历史示例会话（只读快照，用于像素回归）；api 模式改为从服务端加载 */
const seedConversations: Conversation[] =
  API_MODE === 'demo'
    ? [
        { id: nid(), title: '望京一居 合同核验', icon: 'fa-file-contract', seed: 'verify', messages: null },
        { id: nid(), title: '候选房源推荐', icon: 'fa-building', seed: 'rec', messages: null },
      ]
    : [];

export const useStore = create<AppState>(() => ({
  currentView: 'chat',
  pageTitle: '新对话',
  houses: [],
  contracts: [],
  convs: seedConversations,
  activeId: null,
  started: false,
  prefs: { ...initialPrefs, soft: { ...initialPrefs.soft } },
  ctx: { houseId: null, contractId: null },
  recView: 'mix',
  serviceOnline: true,
  hf: { q: '', filter: 'all', sort: 'default' },
  generating: false,
  inputText: '',
  attachments: [],
  toast: null,
  confirmModal: { open: false, title: '', desc: '', okText: '删除', onOk: null },
  houseDrawer: { open: false, houseId: null, anchor: null },
  contractDrawer: { open: false, contractId: null, clauseId: null },
  prefsOpen: false,
  importModal: { open: false, tab: 'paste', panel: 'paste' },
  importProgress: null,
  pendingRows: [],
  pendingTitle: 'AI 提取结果',
  pendingCount: '',
  pendingSource: '',
  pendingError: null,
  importFail: null,
  importTexts: { paste: '', batch: '' },
}));
