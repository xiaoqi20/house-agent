import { useEffect } from 'react';
import { useStore } from '../store';
import { openBindEntry, openImport, openContract, send, startRecommend } from '../controller';
import { Composer } from './Composer';
import { MessageView } from './MessageView';

function EmptyState() {
  return (
    <div id="emptyState" className="min-h-full flex flex-col items-center justify-center px-6 py-10">
      <div className="w-11 h-11 rounded-2xl bg-brand-50 flex items-center justify-center mb-5 fade-in">
        <img src="/mark-96.png" alt="RentGraph" className="w-7 h-7" />
      </div>
      <h1
        className="text-2xl md:text-[28px] md:leading-8 font-semibold text-gray-900 tracking-tight fade-in"
        style={{ animationDelay: '.05s' }}
      >
        你好，我是你的租房 Agent
      </h1>
      <p className="text-sm text-gray-500 mt-2.5 mb-9 fade-in" style={{ animationDelay: '.1s' }}>
        问我租房问题，或上传合同、粘贴房源信息，我会帮你分析并给出建议
      </p>

      <div id="heroSlot" className="w-full max-w-2xl fade-in" style={{ animationDelay: '.15s' }}>
        <Composer />
      </div>

      <div
        className="flex flex-wrap justify-center gap-5 w-full max-w-2xl mt-8 mb-2 fade-in px-4"
        style={{ animationDelay: '.2s' }}
      >
        <button
          onClick={() => openImport('paste')}
          className="group w-36 h-32 text-left bg-yellow-50 border border-yellow-200 rounded-2xl shadow-sm hover:shadow-md transform -rotate-6 hover:rotate-0 hover:-translate-y-1.5 transition-all duration-300 p-4 flex flex-col"
        >
          <div className="w-8 h-8 rounded-full bg-yellow-100 text-yellow-600 flex items-center justify-center mb-auto group-hover:scale-110 transition-transform">
            <i className="fas fa-paste text-sm"></i>
          </div>
          <span className="text-[13px] font-semibold text-yellow-900 leading-snug">
            添加房源
            <br />
            <span className="text-[10px] font-normal text-yellow-600">粘贴 / 手动填写单条</span>
          </span>
        </button>
        <button
          onClick={() => openImport('batch')}
          className="group w-36 h-32 text-left bg-green-50 border border-green-200 rounded-2xl shadow-sm hover:shadow-md transform rotate-3 hover:rotate-0 hover:-translate-y-1.5 transition-all duration-300 p-4 flex flex-col mt-3"
        >
          <div className="w-8 h-8 rounded-full bg-green-100 text-green-600 flex items-center justify-center mb-auto group-hover:scale-110 transition-transform">
            <i className="fas fa-layer-group text-sm"></i>
          </div>
          <span className="text-[13px] font-semibold text-green-900 leading-snug">
            批量导入
            <br />
            <span className="text-[10px] font-normal text-green-600">批量粘贴 / Excel / Word</span>
          </span>
        </button>
        <button
          onClick={startRecommend}
          className="group w-36 h-32 text-left bg-purple-50 border border-purple-200 rounded-2xl shadow-sm hover:shadow-md transform -rotate-3 hover:rotate-0 hover:-translate-y-1.5 transition-all duration-300 p-4 flex flex-col"
        >
          <div className="w-8 h-8 rounded-full bg-purple-100 text-purple-600 flex items-center justify-center mb-auto group-hover:scale-110 transition-transform">
            <i className="fas fa-filter text-sm"></i>
          </div>
          <span className="text-[13px] font-semibold text-purple-900 leading-snug">
            开始筛选
            <br />
            <span className="text-[10px] font-normal text-purple-600">硬约束与软偏好</span>
          </span>
        </button>
      </div>

      <div className="flex flex-wrap justify-center gap-x-5 gap-y-1.5 mt-5 fade-in" style={{ animationDelay: '.25s' }}>
        <button
          onClick={() => openImport('manual')}
          className="text-xs text-gray-400 hover:text-brand-600 transition-colors"
        >
          <i className="fas fa-pen-to-square mr-1"></i>手动填写房源
        </button>
        <button onClick={openBindEntry} className="text-xs text-gray-400 hover:text-brand-600 transition-colors">
          <i className="fas fa-file-shield mr-1"></i>审查已绑定合同
        </button>
        <button
          onClick={() => send('押金不退怎么办？')}
          className="text-xs text-gray-400 hover:text-brand-600 transition-colors"
        >
          <i className="fas fa-book-open mr-1"></i>问租房常识
        </button>
      </div>

      <p
        className="text-[11px] text-gray-400 mt-9 flex items-center gap-1.5 fade-in"
        style={{ animationDelay: '.3s' }}
      >
        <i className="fas fa-clock text-[10px]"></i>候选房源和合同仅用于本次工作台 · 比较范围 3—10 套
      </p>
    </div>
  );
}

export function ChatView({ visible }: { visible: boolean }) {
  const started = useStore((s) => s.started);
  const activeId = useStore((s) => s.activeId);
  const convs = useStore((s) => s.convs);
  const conv = convs.find((c) => c.id === activeId);
  const messages = conv?.messages || [];

  // 与原型一致：新增消息、流式输出和步骤更新时自动滚到底部
  useEffect(() => {
    const v = document.getElementById('chatView');
    if (v) v.scrollTop = v.scrollHeight;
  }, [messages]);

  return (
    <div id="view-chat" className={`${visible ? '' : 'hidden'} flex-1 flex flex-col min-h-0`}>
      <div
        className="flex-1 overflow-y-auto custom-scrollbar"
        id="chatView"
        onClick={(e) => {
          const target = e.target as HTMLElement;
          const btn = target.closest('[data-cite]');
          if (btn) {
            openContract(Number(btn.getAttribute('data-cite')), btn.getAttribute('data-cid'));
            return;
          }
          const followup = target.closest('[data-followup]');
          if (followup) send(followup.getAttribute('data-followup') || '');
        }}
      >
        {!started ? (
          <EmptyState />
        ) : (
          <div id="thread" className="max-w-3xl mx-auto px-6 py-8 space-y-7">
            {messages.map((m) => (
              <MessageView key={m.id} msg={m} />
            ))}
          </div>
        )}
      </div>

      <div id="dock" className={`${started ? '' : 'hidden'} px-4 pb-4 pt-1 shrink-0`}>
        <div id="dockSlot" className="max-w-3xl mx-auto">
          {started ? <Composer /> : null}
        </div>
        <p className="text-[10px] text-center text-gray-400 mt-2">
          回答基于你导入的房源、合同与公开租房知识，仅供参考，不构成法律意见
        </p>
      </div>
    </div>
  );
}
