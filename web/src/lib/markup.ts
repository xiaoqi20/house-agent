import { esc } from './utils';

/** 消息等待中的打字动画（与原型一致） */
export function typingDotsHTML(): string {
  return `<div class="inline-flex items-center gap-1.5 py-2" id="typing">
        <span class="typing-dot w-1.5 h-1.5 rounded-full bg-gray-400 inline-block"></span>
        <span class="typing-dot w-1.5 h-1.5 rounded-full bg-gray-400 inline-block"></span>
        <span class="typing-dot w-1.5 h-1.5 rounded-full bg-gray-400 inline-block"></span></div>`;
}

/** 合同上传进度卡（作为用户消息展示） */
export function uploadCardHTML(
  name: string,
  size: string,
  isPdf: boolean,
  percent: number,
  statusHtml: string,
  redBar: boolean,
): string {
  return `<div class="bg-white border border-gray-200 rounded-2xl rounded-tr-md px-3 py-2.5 shadow-sm w-[280px]" role="status" aria-live="polite">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-lg ${
              isPdf ? 'bg-red-50 text-red-500 border-red-100' : 'bg-gray-50 text-gray-400 border-gray-200'
            } flex items-center justify-center border shrink-0"><i class="fas fa-file${isPdf ? '-pdf' : ''}"></i></div>
            <div class="text-left min-w-0 flex-1">
              <div class="text-[13px] font-medium text-gray-900 truncate">${esc(name)}</div>
              <div class="text-[11px] text-gray-500 upload-status">${statusHtml}</div>
            </div>
          </div>
          <div class="h-1 bg-gray-100 rounded-full mt-2.5 overflow-hidden"><div class="upload-bar h-full ${
            redBar ? 'bg-red-300' : 'bg-brand-500'
          } rounded-full" style="width:${percent}%"></div></div>
        </div>`;
}
