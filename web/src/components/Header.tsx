import { useStore } from '../store';
import { isApiMode, renameActiveConv, toast } from '../controller';

export function Header() {
  const pageTitle = useStore((s) => s.pageTitle);
  const currentView = useStore((s) => s.currentView);
  const serviceOnline = useStore((s) => s.serviceOnline);

  return (
    <header className="h-14 flex items-center justify-between px-5 shrink-0 border-b border-gray-100/80">
      <div className="flex items-center gap-2 min-w-0">
        <h2 className="text-[14px] font-medium text-gray-900 truncate" id="pageTitle">
          {pageTitle}
        </h2>
        {currentView === 'chat' && (
          <button
            id="titleEditBtn"
            className="text-gray-300 hover:text-gray-500 transition-colors"
            title="重命名会话"
            onClick={renameActiveConv}
          >
            <i className="fas fa-pen text-[10px]"></i>
          </button>
        )}
      </div>
      <div className="flex items-center gap-3">
        {serviceOnline ? (
          <span className="hidden sm:flex items-center gap-1.5 text-[11px] text-gray-400 border border-gray-200 rounded-full px-2.5 py-1">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-500"></span>
            </span>
            Agent 在线
          </span>
        ) : (
          <span className="hidden sm:flex items-center gap-1.5 text-[11px] text-red-500 border border-red-200 bg-red-50 rounded-full px-2.5 py-1">
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-red-500"></span>
            {isApiMode ? '服务不可用' : '服务异常（演示）'}
          </span>
        )}
        <button
          onClick={() => toast('分享会话为演示能力，暂未开放')}
          className="w-8 h-8 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 flex items-center justify-center transition-colors"
          title="分享会话（复制 Markdown 文本）"
        >
          <i className="fas fa-arrow-up-from-bracket text-xs"></i>
        </button>
      </div>
    </header>
  );
}
