import type { ConversationSeed, Message, Preferences } from '../types';
import { answerFor } from './answers';
import { clonePrefs, getDemoStore } from '../data/demo';
import { nid } from './utils';

export function textBubble(text: string): string {
  return `<div class="text-[14px] text-gray-800 leading-relaxed bg-gray-100 rounded-2xl rounded-tr-md px-4 py-2.5">${String(text)
    .replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string)
    .replace(/\n/g, '<br>')}</div>`;
}

/** 历史演示会话的种子内容（只读快照，与原型 buildSeed 一致） */
export function buildSeed(seed?: ConversationSeed, currentPrefs?: Preferences): Message[] {
  const store = getDemoStore();
  if (seed === 'rec') {
    return [
      {
        id: nid(),
        role: 'user',
        content: { type: 'html', html: textBubble('预算 6,000、通勤 45 分钟以内、必须独立卫浴，帮我推荐') },
      },
      {
        id: nid(),
        role: 'ai',
        actions: true,
        content: {
          type: 'recommend',
          variant: 'demo',
          demoPrefs: clonePrefs(currentPrefs ?? demoDefaultPrefs),
        },
      },
    ];
  }
  if (seed === 'verify') {
    const h = store.targetHouse;
    const c = store.targetContract;
    return [
      {
        id: nid(),
        role: 'user',
        content: {
          type: 'html',
          html: `<div class="bg-white border border-gray-200 rounded-2xl rounded-tr-md px-3 py-2.5 flex items-center gap-3 shadow-sm">
            <div class="w-9 h-9 rounded-lg bg-red-50 flex items-center justify-center text-red-500 border border-red-100 shrink-0"><i class="fas fa-file-pdf"></i></div>
            <div class="text-left min-w-0"><div class="text-[13px] font-medium text-gray-900 truncate">北京市房屋租赁合同（望京）.pdf</div><div class="text-[11px] text-gray-500">2.4 MB · 绑定 ${h.no} · 演示快照</div></div></div>`,
        },
      },
      {
        id: nid(),
        role: 'ai',
        actions: true,
        content: { type: 'verify', houseId: h.id, contractId: c.id, readOnly: true },
      },
      { id: nid(), role: 'user', content: { type: 'html', html: textBubble('物业费谁承担？') } },
      {
        id: nid(),
        role: 'ai',
        actions: true,
        content: {
          type: 'html',
          html: `<div class="text-[14px] text-gray-800 leading-7">${answerFor('物业费谁承担？', h, c)}</div>`,
        },
      },
    ];
  }
  return [];
}

const demoDefaultPrefs: Preferences = {
  budget: 6000,
  commute: 45,
  needBathroom: true,
  allowShared: false,
  soft: { south: false, light: false, highFloor: false, bigArea: false, flexPay: false },
};
