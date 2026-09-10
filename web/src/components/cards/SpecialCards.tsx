import { isApiMode, pastedContractFlow, regenerate, retryAfterOffline, toggleService, triggerFilePick } from '../../controller';
import { DEMO_CONTRACT_TEXT } from '../../data/demo';
import { getHouse } from '../../lib/selectors';

export function StepsCard({
  steps,
  index,
  cancelled,
}: {
  steps: string[];
  index: number;
  cancelled?: boolean;
}) {
  if (cancelled) {
    return (
      <div className="text-[13px] text-gray-400 py-1">
        <i className="fas fa-circle-stop mr-1.5"></i>分析已取消，可点击重新生成重试
      </div>
    );
  }
  return (
    <div
      className="bg-gray-50 border border-gray-100 rounded-2xl px-4 py-3.5 space-y-2 font-medium inline-block"
      role="status"
      aria-live="polite"
    >
      {steps.map((s, j) => (
        <div
          key={j}
          className={`flex items-center gap-2.5 text-[13px] ${
            j < index ? 'text-green-600' : j === index ? 'text-gray-800' : 'text-gray-300'
          }`}
        >
          <i
            className={`fas ${
              j < index ? 'fa-circle-check' : j === index ? 'fa-circle-notch fa-spin' : 'fa-circle'
            } w-4 text-center`}
          ></i>{' '}
          {s}
        </div>
      ))}
    </div>
  );
}

export function BindOptionsCard({ houseId }: { houseId: string }) {
  const h = getHouse(houseId);
  if (!h) return null;
  return (
    <>
      <div className="text-[14px] text-gray-800 mb-2.5 leading-relaxed">
        好的，将为目标房源 <b>{h.no} {h.name}</b> 绑定合同。绑定后我会把房源承诺与合同条款逐项核验：
      </div>
      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-4 flex flex-wrap gap-2.5">
        <button
          onClick={triggerFilePick}
          className="flex items-center gap-2 bg-gray-900 hover:bg-gray-700 text-white text-xs font-medium rounded-xl px-4 py-2.5 transition-colors"
        >
          <i className="fas fa-file-pdf"></i>上传合同 PDF
        </button>
        <button
          onClick={() => pastedContractFlow(DEMO_CONTRACT_TEXT)}
          className="flex items-center gap-2 bg-white border border-gray-200 hover:border-brand-300 text-gray-700 text-xs font-medium rounded-xl px-4 py-2.5 transition-colors"
        >
          <i className="fas fa-paste"></i>粘贴合同文本（点我用示例）
        </button>
        <span className="w-full text-[10px] text-gray-300">
          {isApiMode
            ? '支持 PDF（文字版）/ Word(.docx) / 文本文件；图片仅存档、暂不做 OCR'
            : '一期支持 PDF 与粘贴文本；Word / 图片 OCR 为规划能力'}
        </span>
      </div>
    </>
  );
}

export function OfflineCard({ failedPrompt }: { failedPrompt: string }) {
  return (
    <>
      <div className="text-[14px] text-gray-800 leading-7">
        <p className="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5">
          <i className="fas fa-cloud-bolt text-red-400"></i> 回答失败
        </p>
        服务暂时不可用（网络或服务异常），你的对话与上下文已保留。
      </div>
      <div className="mt-2.5 flex gap-2">
        <button
          onClick={() => retryAfterOffline(failedPrompt)}
          className="text-xs bg-gray-900 text-white rounded-xl px-4 py-2.5"
        >
          <i className="fas fa-rotate-right mr-1"></i>恢复服务并重试
        </button>
        <button onClick={toggleService} className="text-xs bg-white border border-gray-200 rounded-xl px-4 py-2.5">
          仅恢复服务
        </button>
      </div>
    </>
  );
}

/** 后端错误码 → 可执行提示（文案来自服务端 message / hint） */
export function ApiErrorCard({
  code,
  message,
  hint,
  canPasteText,
}: {
  code: string;
  message: string;
  hint: string;
  canPasteText?: boolean;
}) {
  return (
    <>
      <div className="text-[14px] text-gray-800 leading-7">
        <p className="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5">
          <i className="fas fa-circle-exclamation text-amber-500"></i> 处理失败
        </p>
        {message}
        {hint && (
          <div className="mt-2 text-[12px] text-gray-500 bg-gray-50 border border-gray-100 rounded-xl px-3.5 py-2.5">
            <i className="fas fa-lightbulb mr-1 text-amber-500"></i>
            {hint}
          </div>
        )}
        <div className="text-[10px] text-gray-300 mt-1.5">错误码：{code}</div>
      </div>
      <div className="mt-2.5 flex flex-wrap gap-2">
        <button onClick={regenerate} className="text-xs bg-gray-900 text-white rounded-xl px-4 py-2.5">
          <i className="fas fa-rotate-right mr-1"></i>重试
        </button>
        {canPasteText && (
          <button
            onClick={() => document.getElementById('chatInput')?.focus()}
            className="text-xs bg-white border border-gray-200 rounded-xl px-4 py-2.5"
          >
            <i className="fas fa-paste mr-1"></i>粘贴合同文本
          </button>
        )}
      </div>
    </>
  );
}

export function ContractTooShortCard() {
  return (
    <>
      <div className="text-[14px] text-gray-800 leading-7">
        <p className="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5">
          <i className="fas fa-circle-exclamation text-red-400"></i> 解析失败
        </p>
        文本过短，未识别为有效合同（缺少当事人、租期或租金等关键要素）。<br />
        <b>建议：</b>粘贴完整合同全文，或上传 PDF 原件。
      </div>
      <div className="mt-2.5">
        <button
          onClick={() => pastedContractFlow(DEMO_CONTRACT_TEXT)}
          className="text-xs bg-gray-900 text-white rounded-xl px-4 py-2.5"
        >
          <i className="fas fa-rotate-right mr-1"></i>使用示例合同重试
        </button>
      </div>
    </>
  );
}

export function UploadUnsupportedCard() {
  return (
    <div className="text-[14px] text-gray-800 leading-7">
      <p className="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5">
        <i className="fas fa-circle-exclamation text-amber-500"></i> 无法解析该文件
      </p>
      合同入口一期仅支持 <b>PDF</b> 与<b>粘贴文本</b>，Word / 图片（OCR）为规划能力。
      <br />
      你可以：① 把合同导出为 PDF 重新上传；② 直接<b>粘贴合同全文</b>到输入框。
    </div>
  );
}
