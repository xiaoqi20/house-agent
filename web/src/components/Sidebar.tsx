import { useStore } from '../store';
import {
  askDeleteConv,
  newChat,
  openConversation,
  renameConv,
  switchView,
  toast,
} from '../controller';

export function Sidebar() {
  const convs = useStore((s) => s.convs);
  const activeId = useStore((s) => s.activeId);
  const currentView = useStore((s) => s.currentView);
  const houses = useStore((s) => s.houses);
  const contracts = useStore((s) => s.contracts);

  const houseCount = houses.filter((h) => h.status === 'active').length;

  const navItem = (
    view: 'chat' | 'houses' | 'contracts',
    icon: string,
    label: string,
    count?: number,
  ) => (
    <button
      data-view={view}
      onClick={() => switchView(view)}
      className={`nav-item ${
        currentView === view ? 'active' : ''
      } w-full flex items-center gap-3 px-3 py-2 rounded-xl text-[13px] font-medium text-gray-600 border border-transparent hover:bg-gray-200/50 transition-colors`}
    >
      <i className={`fas ${icon} w-4 text-center text-gray-400`}></i> {label}
      {count !== undefined && (
        <span className="ml-auto text-[10px] bg-gray-200 text-gray-500 font-semibold px-1.5 py-0.5 rounded-md">
          {count}
        </span>
      )}
    </button>
  );

  return (
    <aside className="w-[260px] bg-[#f7f7f8] border-r border-gray-200/80 flex-col shrink-0 hidden md:flex">
      <div className="h-14 flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-2.5">
          <img src="/mark-96.png" alt="RentGraph" className="w-7 h-7 shrink-0" />
          <span className="font-semibold text-[15px] tracking-tight text-gray-900">RentGraph</span>
          <span className="px-1.5 py-0.5 bg-gray-200/80 text-gray-500 text-[10px] font-semibold rounded">Beta</span>
        </div>
      </div>

      <div className="px-3 pt-1">
        <button
          onClick={newChat}
          className="w-full bg-white border border-gray-200 hover:border-gray-300 hover:shadow-sm text-gray-800 px-3.5 py-2.5 rounded-xl text-[13px] font-medium transition-all flex items-center gap-2.5"
        >
          <i className="fas fa-plus text-xs text-gray-500"></i> 新对话
          <span className="ml-auto text-[10px] text-gray-400 border border-gray-200 rounded px-1 py-0.5">⌘N</span>
        </button>
      </div>

      <nav className="px-3 mt-4 space-y-0.5" id="mainNav">
        {navItem('chat', 'fa-comments', '对话工作台')}
        {navItem('houses', 'fa-building', '本次候选房源', houseCount)}
        {navItem('contracts', 'fa-file-contract', '本次合同', contracts.length)}
      </nav>

      <div className="flex-1 overflow-y-auto custom-scrollbar px-3 mt-6">
        <div className="text-[11px] font-medium text-gray-400 px-3 mb-1.5">最近对话</div>
        <div className="space-y-0.5" id="chatList">
          {convs.length === 0 ? (
            <div className="text-[11px] text-gray-300 px-3 py-2">暂无历史对话</div>
          ) : (
            convs.map((c) => (
              <div className="chat-item group relative" key={c.id}>
                <button
                  onClick={() => openConversation(c.id)}
                  className={`w-full text-left pl-3 pr-14 py-2 rounded-lg text-[13px] truncate transition-colors ${
                    c.id === activeId ? 'text-gray-800 bg-gray-200/60' : 'text-gray-600 hover:bg-gray-200/60'
                  }`}
                >
                  <i className={`fas ${c.icon} text-[10px] text-gray-400 mr-2`}></i>
                  {c.title}
                </button>
                <div className="chat-ops absolute right-1.5 top-1/2 -translate-y-1/2 flex gap-0.5">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      renameConv(c.id);
                    }}
                    title="重命名"
                    className="w-6 h-6 rounded-md text-gray-400 hover:text-gray-700 hover:bg-white flex items-center justify-center"
                  >
                    <i className="fas fa-pen text-[10px]"></i>
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      askDeleteConv(c.id);
                    }}
                    title="删除"
                    className="w-6 h-6 rounded-md text-gray-400 hover:text-red-500 hover:bg-white flex items-center justify-center"
                  >
                    <i className="fas fa-trash-can text-[10px]"></i>
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="px-3 pb-2">
        <div className="text-[10px] text-gray-400 leading-relaxed bg-gray-200/40 border border-gray-200/60 rounded-xl px-3 py-2">
          <i className="fas fa-clock mr-1"></i>候选房源与合同属于<b>本次工作台临时数据（有效期 72 小时）</b>，长期保存与跨设备同步暂未承诺。
        </div>
      </div>

      <div className="p-3 border-t border-gray-200/80 mt-auto">
        <div
          className="flex items-center justify-between px-2 py-2 rounded-xl hover:bg-gray-200/60 cursor-pointer transition-colors group"
          title="本次工作台临时数据"
          onClick={() => toast('本次工作台临时数据有效期 72 小时，长期存储暂未开放')}
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="relative shrink-0">
              <div className="w-8 h-8 rounded-full bg-blue-100 border border-blue-200 flex items-center justify-center text-blue-700 font-semibold text-xs">
                <i className="fas fa-database text-xs"></i>
              </div>
              <div className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-green-500 border-2 border-[#f7f7f8] rounded-full"></div>
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[13px] font-medium text-gray-900 truncate">本次工作台</div>
              <div className="text-[11px] text-gray-400 truncate">临时数据 · 有效期 72 小时</div>
            </div>
          </div>
          <i className="fas fa-gear text-gray-400 group-hover:text-gray-600 px-1 transition-colors text-xs"></i>
        </div>
      </div>
    </aside>
  );
}
