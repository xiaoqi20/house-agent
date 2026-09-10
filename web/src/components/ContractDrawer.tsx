import { useEffect } from 'react';
import { useStore } from '../store';
import { getContract } from '../lib/selectors';
import { useDrawerTransition } from '../lib/useDrawerTransition';
import { closeContract } from '../controller';

function ScrollToClause({ clauseId }: { clauseId: number }) {
  useEffect(() => {
    const timer = setTimeout(() => {
      document.getElementById('cl-' + clauseId)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 350);
    return () => clearTimeout(timer);
  }, [clauseId]);
  return null;
}

export function ContractDrawer() {
  const { open, contractId, clauseId } = useStore((s) => s.contractDrawer);
  useStore((s) => s.contracts);
  const { mounted, shown } = useDrawerTransition(open);
  const target = contractId ? getContract(contractId) : null;

  if (!mounted || !target) return null;
  const demoBadge = target.isDemoParse || target.name.includes('演示解析');

  return (
    <>
      <div id="overlay" className={`${shown ? '' : 'hidden'} fixed inset-0 bg-black/20 z-30`} onClick={closeContract}></div>
      <aside
        id="contractDrawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawerTitle"
        aria-hidden={!shown}
        inert={!shown}
        className={`${
          shown ? '' : 'translate-x-full'
        } fixed inset-y-0 right-0 w-full max-w-md bg-white shadow-2xl z-40 transform transition-transform duration-300 flex flex-col`}
      >
        <div className="h-16 flex items-center justify-between px-5 border-b border-gray-100 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-lg bg-red-50 flex items-center justify-center text-red-500 border border-red-100 shrink-0">
              <i className="fas fa-file-pdf"></i>
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-gray-900 truncate" id="drawerTitle">
                {target.name}{' '}
                {demoBadge && (
                  <span className="text-[10px] font-normal bg-amber-100 text-amber-700 border border-amber-200 rounded px-1.5 py-0.5 align-middle ml-1">
                    演示解析
                  </span>
                )}
              </div>
              <div className="text-[11px] text-gray-500" id="drawerMeta">
                {target.no} · 已解析 {target.clausesList.length} 项条款{target.size ? ' · ' + target.size : ''}
              </div>
            </div>
          </div>
          <button
            onClick={closeContract}
            aria-label="关闭合同抽屉"
            className="w-8 h-8 rounded-lg hover:bg-gray-100 text-gray-400 flex items-center justify-center shrink-0"
          >
            <i className="fas fa-times"></i>
          </button>
        </div>
        <div
          className="flex-1 overflow-y-auto custom-scrollbar p-6 text-[13px] leading-7 text-gray-600 space-y-5"
          id="contractBody"
        >
          {target.clausesList.map(([id, title, text]) => {
            const risky = target.riskClauses.includes(id);
            return (
              <div key={id}>
                <div className={risky ? 'pl-3 border-l-2 border-amber-300' : ''}>
                  <h4 className="text-sm font-semibold text-gray-900 mb-1">{title}</h4>
                  <p>{risky ? <mark className="clause">{text}</mark> : text}</p>
                  {risky && (
                    <div className="text-[11px] text-amber-600 mt-1">
                      <i className="fas fa-triangle-exclamation mr-1"></i>与房源承诺冲突或存在风险
                    </div>
                  )}
                </div>
                <div id={'cl-' + id}></div>
              </div>
            );
          })}
        </div>
        <div className="p-4 border-t border-gray-100 shrink-0 flex items-center gap-2">
          <i className="fas fa-highlighter text-amber-500 text-sm"></i>
          <span className="text-xs text-gray-500">黄色高亮 = 与房源承诺冲突或风险条款，点击核验项可跳转定位</span>
        </div>
      </aside>
      {shown && clauseId != null ? <ScrollToClause key={clauseId} clauseId={clauseId} /> : null}
    </>
  );
}
