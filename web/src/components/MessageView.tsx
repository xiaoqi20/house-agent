import { memo, useRef, useState } from 'react';
import type { Message } from '../types';
import { regenerate, toast } from '../controller';
import { RecommendCard } from './cards/RecommendCard';
import { VerifyCard } from './cards/VerifyCard';
import {
  ApiErrorCard,
  BindOptionsCard,
  ContractTooShortCard,
  OfflineCard,
  StepsCard,
  UploadUnsupportedCard,
} from './cards/SpecialCards';

function MessageContent({ msg }: { msg: Message }) {
  const c = msg.content;
  switch (c.type) {
    case 'html':
      return <div dangerouslySetInnerHTML={{ __html: c.html }} />;
    case 'steps':
      return <StepsCard steps={c.steps} index={c.index} cancelled={c.cancelled} />;
    case 'recommend':
      if (c.variant === 'server') return <RecommendCard variant="server" data={c.data} />;
      return c.variant === 'live' ? (
        <RecommendCard variant="live" snapshot={c.snapshot} />
      ) : (
        <RecommendCard variant="demo" demoPrefs={c.demoPrefs} />
      );
    case 'verify':
      return (
        <VerifyCard houseId={c.houseId} contractId={c.contractId} readOnly={c.readOnly} data={c.data} />
      );
    case 'bind-options':
      return <BindOptionsCard houseId={c.houseId} />;
    case 'offline':
      return <OfflineCard failedPrompt={c.failedPrompt} />;
    case 'contract-too-short':
      return <ContractTooShortCard />;
    case 'upload-unsupported':
      return <UploadUnsupportedCard />;
    case 'api-error':
      return <ApiErrorCard code={c.code} message={c.message} hint={c.hint} canPasteText={c.canPasteText} />;
    default:
      return null;
  }
}

export const MessageView = memo(function MessageView({ msg }: { msg: Message }) {
  const [copied, setCopied] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  if (msg.role === 'user') {
    return (
      <div className="flex justify-end msg-enter">
        <div className="max-w-[85%]">
          <MessageContent msg={msg} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3.5 msg-enter ai-msg group">
      <div className="w-7 h-7 rounded-lg bg-brand-50 flex items-center justify-center shrink-0 mt-0.5">
        <img src="/mark-96.png" alt="RentGraph" className="w-[18px] h-[18px]" />
      </div>
      <div className="flex-1 min-w-0 pt-0.5">
        <div className="ai-body" ref={bodyRef}>
          <MessageContent msg={msg} />
        </div>
        {msg.actions && (
          <div className="msg-actions flex items-center gap-1 mt-2">
            <button
              onClick={() => {
                navigator.clipboard?.writeText(bodyRef.current?.innerText || '');
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
                toast('已复制到剪贴板');
              }}
              title="复制"
              className="w-7 h-7 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 flex items-center justify-center transition-colors"
            >
              <i className={`fas ${copied ? 'fa-check text-green-500' : 'fa-copy'} text-[11px]`}></i>
            </button>
            <button
              onClick={regenerate}
              title="重新生成"
              className="w-7 h-7 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 flex items-center justify-center transition-colors"
            >
              <i className="fas fa-rotate-right text-[11px]"></i>
            </button>
            <button
              onClick={() => toast('感谢反馈（演示）')}
              title="有帮助"
              className="w-7 h-7 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 flex items-center justify-center transition-colors"
            >
              <i className="fas fa-thumbs-up text-[11px]"></i>
            </button>
          </div>
        )}
      </div>
    </div>
  );
});
