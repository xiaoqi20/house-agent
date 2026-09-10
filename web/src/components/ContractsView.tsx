import { useStore } from '../store';
import type { Contract } from '../types';
import { getHouse } from '../lib/selectors';
import {
  askDeleteContract,
  openContract,
  openBindEntry,
  retryFailedContract,
  showVerificationCard,
  switchView,
} from '../controller';

function ContractCard({ c }: { c: Contract }) {
  const ctx = useStore((s) => s.ctx);
  useStore((s) => s.houses);
  const h = c.boundHouseId ? getHouse(c.boundHouseId) : null;

  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-4 hover:shadow-[0_2px_10px_rgba(0,0,0,0.04)] transition-shadow">
      <div className="flex items-start gap-3.5">
        <div
          className={`w-10 h-10 rounded-xl ${
            c.status === 'failed' ? 'bg-gray-50 text-gray-400 border-gray-200' : 'bg-red-50 text-red-500 border-red-100'
          } border flex items-center justify-center shrink-0`}
        >
          <i className="fas fa-file-pdf"></i>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] font-bold text-gray-400 bg-gray-100 rounded px-1.5 py-0.5">{c.no}</span>
            <span className="text-[14px] font-medium text-gray-900 truncate">{c.name}</span>
            {c.status === 'done' ? (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-green-50 text-green-600 border border-green-100">
                已完成
              </span>
            ) : (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-red-50 text-red-500 border border-red-100">
                失败
              </span>
            )}
            {ctx.contractId === c.id && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-brand-50 text-brand-600 border border-brand-100">
                当前合同
              </span>
            )}
          </div>
          <div className="text-[11px] text-gray-400 mt-1 flex items-center gap-2 flex-wrap">
            <span>
              <i className="fas fa-arrow-up-from-bracket text-[9px] mr-1"></i>
              {c.source}
            </span>
            <span>{c.time}</span>
            {h ? (
              <span className="text-emerald-600">
                <i className="fas fa-link text-[9px] mr-0.5"></i>绑定 {h.no} {h.name}
              </span>
            ) : (
              <span>未绑定房源</span>
            )}
            {c.status === 'failed' && <span className="text-red-400">{c.reason}</span>}
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {c.status === 'done' && (
            <>
              <button
                onClick={() => openContract(null, c.id)}
                className="h-8 px-2.5 rounded-lg text-xs text-gray-500 hover:text-gray-800 hover:bg-gray-100 transition-colors"
              >
                <i className="fas fa-file-lines mr-1"></i>原文
              </button>
              {h && (
                <button
                  onClick={() => showVerificationCard(h.id)}
                  className="h-8 px-2.5 rounded-lg text-xs text-brand-600 hover:bg-brand-50 transition-colors"
                >
                  <i className="fas fa-code-compare mr-1"></i>核验
                </button>
              )}
            </>
          )}
          {c.status === 'failed' && (
            <button
              onClick={() => retryFailedContract(c.id)}
              className="h-8 px-2.5 rounded-lg text-xs text-brand-600 hover:bg-brand-50 transition-colors"
            >
              <i className="fas fa-rotate-right mr-1"></i>重新解析
            </button>
          )}
          <button
            onClick={() => askDeleteContract(c.id)}
            title="删除"
            className="w-8 h-8 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
          >
            <i className="fas fa-trash-can text-[11px]"></i>
          </button>
        </div>
      </div>
    </div>
  );
}

export function ContractsView({ visible }: { visible: boolean }) {
  const contracts = useStore((s) => s.contracts);

  return (
    <div id="view-contracts" className={`${visible ? '' : 'hidden'} flex-1 overflow-y-auto custom-scrollbar`}>
      <div className="max-w-3xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-lg font-semibold text-gray-900">本次合同</h1>
            <p className="text-xs text-gray-400 mt-1">绑定到候选房源的合同，仅用于本次工作台</p>
          </div>
          <button
            onClick={openBindEntry}
            className="bg-gray-900 hover:bg-gray-700 text-white text-xs font-medium rounded-xl px-4 py-2.5 transition-colors flex items-center gap-1.5"
          >
            <i className="fas fa-plus text-[10px]"></i> 绑定合同
          </button>
        </div>
        <div id="contractList" className="space-y-3">
          {contracts.length === 0 ? (
            <div className="text-center py-16 text-gray-400">
              <i className="fas fa-file-circle-question text-3xl mb-3 text-gray-200"></i>
              <div className="text-[13px]">还没有合同。先在候选房源中选定目标房源，再绑定合同进行核验。</div>
              <button
                onClick={() => switchView('houses')}
                className="mt-4 text-xs bg-gray-900 text-white rounded-xl px-4 py-2.5"
              >
                去看候选房源
              </button>
            </div>
          ) : (
            contracts.map((c) => <ContractCard key={c.id} c={c} />)
          )}
        </div>
      </div>
    </div>
  );
}
