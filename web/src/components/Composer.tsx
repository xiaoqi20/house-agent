import { useStore } from '../store';
import {
  addPendingAttachment,
  openImport,
  removeCtx,
  removePendingAttachment,
  stopGenerating,
  submitInput,
  toast,
  triggerFilePick,
} from '../controller';
import { getContract, getHouse } from '../lib/selectors';
import { fmtSize } from '../lib/utils';

export function Composer() {
  const inputText = useStore((s) => s.inputText);
  const attachments = useStore((s) => s.attachments);
  const ctx = useStore((s) => s.ctx);
  const generating = useStore((s) => s.generating);
  // 订阅数据，保证上下文标签随房源 / 合同更新
  useStore((s) => s.houses);
  useStore((s) => s.contracts);

  const h = ctx.houseId ? getHouse(ctx.houseId) : null;
  const c = ctx.contractId ? getContract(ctx.contractId) : null;
  const hasChips = !!h || !!c;

  return (
    <div>
      <div id="contextChips" className={`${hasChips ? 'flex' : 'hidden'} flex-wrap gap-1.5 mb-2 px-1`}>
        {h && (
          <span className="inline-flex items-center gap-1.5 text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-full pl-2.5 pr-1.5 py-1">
            <i className="fas fa-building text-[10px]"></i>
            <span className="max-w-[160px] truncate">
              {h.no} {h.name}
            </span>
            <span className="text-emerald-400">· 当前房源</span>
            <button
              onClick={() => removeCtx('house')}
              title="移除上下文"
              className="w-4 h-4 rounded-full hover:bg-emerald-100 text-emerald-400 flex items-center justify-center"
            >
              <i className="fas fa-xmark text-[9px]"></i>
            </button>
          </span>
        )}
        {c && (
          <span className="inline-flex items-center gap-1.5 text-[11px] text-red-600 bg-red-50 border border-red-100 rounded-full pl-2.5 pr-1.5 py-1">
            <i className="fas fa-file-pdf text-[10px]"></i>
            <span className="max-w-[160px] truncate">
              {c.no} {c.name}
            </span>
            <span className="text-red-300">· 当前合同</span>
            <button
              onClick={() => removeCtx('contract')}
              title="移除上下文"
              className="w-4 h-4 rounded-full hover:bg-red-100 text-red-400 flex items-center justify-center"
            >
              <i className="fas fa-xmark text-[9px]"></i>
            </button>
          </span>
        )}
      </div>

      <div id="attachChips" className={`${attachments.length ? 'flex' : 'hidden'} flex-wrap gap-1.5 mb-2 px-1`}>
        {attachments.map((a) => {
          const isPdf = /\.pdf$/i.test(a.file.name);
          return (
            <span
              key={a.id}
              className="inline-flex items-center gap-2 text-[11px] text-gray-600 bg-gray-100 border border-gray-200 rounded-xl p-1.5 pr-2"
            >
              <span
                className={`w-8 h-8 rounded-lg ${
                  isPdf ? 'bg-red-50 text-red-500' : 'bg-white text-gray-400'
                } border border-gray-200 flex items-center justify-center shrink-0`}
              >
                <i className={`fas fa-file${isPdf ? '-pdf' : ''} text-xs`}></i>
              </span>
              <span className="min-w-0">
                <span className="block max-w-[140px] truncate">{a.file.name}</span>
                <span className="block text-[10px] text-gray-400">{fmtSize(a.file.size)}</span>
              </span>
              <button
                onClick={() => removePendingAttachment(a.id)}
                title="移除"
                className="w-4 h-4 rounded-full hover:bg-gray-200 text-gray-400 flex items-center justify-center shrink-0"
              >
                <i className="fas fa-xmark text-[9px]"></i>
              </button>
            </span>
          );
        })}
      </div>

      <div className="bg-white border border-gray-200 rounded-3xl shadow-[0_2px_12px_rgba(0,0,0,0.05)] p-2.5 focus-within:border-gray-300 focus-within:shadow-[0_4px_20px_rgba(0,0,0,0.08)] transition-all">
        <textarea
          id="chatInput"
          rows={2}
          value={inputText}
          onChange={(e) => useStore.setState({ inputText: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submitInput();
            }
          }}
          onPaste={(e) => {
            const files = Array.from(e.clipboardData?.files || []);
            if (!files.length) return;
            e.preventDefault();
            files.forEach(addPendingAttachment);
          }}
          className="w-full bg-transparent resize-none outline-none text-sm px-2.5 py-1.5 text-gray-800 placeholder:text-gray-400 custom-scrollbar max-h-40"
          placeholder="描述预算 / 通勤 / 居住要求，或粘贴房源、合同文本…"
        ></textarea>
        <div className="flex justify-between items-center px-1">
          <div className="flex gap-0.5 items-center">
            <button
              onClick={triggerFilePick}
              title="上传合同 (PDF)"
              className="w-8 h-8 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 flex items-center justify-center transition-colors"
            >
              <i className="fas fa-paperclip text-sm"></i>
            </button>
            <button
              onClick={() => openImport('batch')}
              title="导入房源（批量粘贴 / Excel / Word / 文本）"
              className="w-8 h-8 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 flex items-center justify-center transition-colors"
            >
              <i className="fas fa-file-import text-sm"></i>
            </button>
            <button
              onClick={() => toast('图片 OCR 为规划能力，暂不支持识别图中文字')}
              title="图片（规划能力）"
              className="w-8 h-8 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 flex items-center justify-center transition-colors"
            >
              <i className="fas fa-image text-sm"></i>
            </button>
            <span className="hidden sm:flex items-center text-[10px] text-gray-300 ml-1.5 gap-1">
              <i className="fas fa-link text-[9px]"></i>附件自动加入当前对话
            </span>
          </div>
          {generating ? (
            <button
              onClick={stopGenerating}
              className="bg-gray-900 hover:bg-gray-700 text-white rounded-full w-8 h-8 flex items-center justify-center shadow-sm transition-colors"
              title="停止生成"
            >
              <i className="fas fa-stop text-[10px]"></i>
            </button>
          ) : (
            <button
              onClick={submitInput}
              className="bg-gray-900 hover:bg-gray-700 text-white rounded-full w-8 h-8 flex items-center justify-center shadow-sm transition-colors"
              title="发送"
            >
              <i className="fas fa-arrow-up text-xs"></i>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
