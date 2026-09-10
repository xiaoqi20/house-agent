import { useStore } from '../store';
import type { House } from '../types';
import { SOURCE_LABEL } from '../data/demo';
import { completeness, comparisonMissingFields, missingFields, monthlyCost } from '../lib/calc';
import { fmt } from '../lib/utils';
import {
  askRemoveHouse,
  bindContractEntry,
  openHouseDrawer,
  openImport,
  setTargetHouse,
  startRecommend,
} from '../controller';

function HouseCard({ h }: { h: House }) {
  const ctx = useStore((s) => s.ctx);
  const comp = completeness(h);
  const miss = missingFields(h);
  const mc = monthlyCost(h);
  const dropped = h.status === 'dropped';
  const isActive = ctx.houseId === h.id;

  return (
    <div
      className={`bg-white border ${
        dropped ? 'border-gray-100 opacity-60' : 'border-gray-200'
      } rounded-2xl p-4 hover:shadow-[0_2px_10px_rgba(0,0,0,0.04)] transition-shadow`}
    >
      <div className="flex items-start gap-3.5">
        <div
          className={`w-10 h-10 rounded-xl ${
            dropped ? 'bg-gray-50 text-gray-300 border-gray-200' : 'bg-emerald-50 text-emerald-600 border-emerald-100'
          } border flex items-center justify-center shrink-0`}
        >
          <i className="fas fa-building"></i>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] font-bold text-gray-400 bg-gray-100 rounded px-1.5 py-0.5">{h.no}</span>
            <span className="text-[14px] font-medium text-gray-900 truncate">{h.name}</span>
            {isActive && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-brand-50 text-brand-600 border border-brand-100">
                当前房源
              </span>
            )}
            {dropped && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-gray-100 text-gray-400 border border-gray-200">
                已放弃
              </span>
            )}
            {comp < 70 && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-50 text-amber-600 border border-amber-100">
                信息不完整
              </span>
            )}
          </div>
          <div className="text-[11px] text-gray-400 mt-1 flex items-center gap-2 flex-wrap">
            <span>
              <i className="fas fa-arrow-up-from-bracket text-[9px] mr-1"></i>
              {SOURCE_LABEL[h.source] || h.source}
            </span>
            {h.batch && <span>批次 {h.batch}</span>}
            <span>
              完整度{' '}
              <b className={comp >= 80 ? 'text-green-600' : comp >= 60 ? 'text-amber-600' : 'text-red-500'}>
                {comp}%
              </b>
            </span>
            {miss.length > 0 && (
              <span className="text-amber-500">
                缺：{miss.slice(0, 3).join('、')}
                {miss.length > 3 ? ' 等' : ''}
              </span>
            )}
          </div>
          <div className="text-[12px] text-gray-600 mt-2 flex items-center gap-x-3 gap-y-1 flex-wrap">
            <span>
              <b className="text-gray-900">{h.rent ? fmt(h.rent) + ' 元/月' : '租金待确认'}</b> ·{' '}
              {h.deposit || '押金待确认'}
            </span>
            <span>
              月度总成本 {mc.unknown.length ? '≈' : ''}
              <b>{fmt(mc.sum)}</b> 元
              {mc.unknown.length > 0 && (
                <span className="text-amber-500 text-[10px]">（{mc.unknown.join('、')}待确认）</span>
              )}
            </span>
            <span>{h.commuteMin ? '通勤 ' + h.commuteMin + ' 分钟' : '通勤待确认'}</span>
            {h.shared ? <span className="text-purple-500">合租</span> : <span>整租</span>}
            {h.bathroom === true ? <span>独立卫浴</span> : h.bathroom === false ? <span className="text-amber-500">无独卫</span> : null}
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0 flex-wrap justify-end max-w-[220px]">
          <button
            onClick={() => openHouseDrawer(h.id)}
            className="h-8 px-2.5 rounded-lg text-xs text-gray-500 hover:text-gray-800 hover:bg-gray-100 transition-colors"
          >
            <i className="fas fa-eye mr-1"></i>详情
          </button>
          {!dropped && ctx.houseId !== h.id && (
            <button
              onClick={() => setTargetHouse(h.id)}
              className="h-8 px-2.5 rounded-lg text-xs text-brand-600 hover:bg-brand-50 transition-colors"
            >
              <i className="fas fa-crosshairs mr-1"></i>设为目标
            </button>
          )}
          {!dropped && (
            <button
              onClick={() => bindContractEntry(h.id)}
              className="h-8 px-2.5 rounded-lg text-xs text-gray-500 hover:text-gray-800 hover:bg-gray-100 transition-colors"
            >
              <i className="fas fa-file-contract mr-1"></i>
              {h.contractId ? '查看核验' : '绑定合同'}
            </button>
          )}
          <button
            onClick={() => askRemoveHouse(h.id)}
            title="移除"
            className="w-8 h-8 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
          >
            <i className="fas fa-trash-can text-[11px]"></i>
          </button>
        </div>
      </div>
    </div>
  );
}

export function HousesView({ visible }: { visible: boolean }) {
  const houses = useStore((s) => s.houses);
  const hf = useStore((s) => s.hf);
  const prefs = useStore((s) => s.prefs);

  const all = houses.filter((h) => h.status === 'active');
  const comparable = all.filter((h) => comparisonMissingFields(h, prefs).length === 0);
  const pendingCount = all.length - comparable.length;
  const pendingText = pendingCount ? `，${pendingCount} 套待完善` : '';

  let hint: React.ReactNode = null;
  if (all.length) {
    if (comparable.length < 3)
      hint = (
        <div className="text-[12px] text-amber-700 bg-amber-50 border border-amber-100 rounded-xl px-4 py-3 flex items-center gap-2">
          <i className="fas fa-circle-info"></i>当前有 {comparable.length} 套关键字段完整可比较{pendingText}，至少需要 3 套完整候选。
        </div>
      );
    else if (comparable.length > 10)
      hint = (
        <div className="text-[12px] text-red-600 bg-red-50 border border-red-100 rounded-xl px-4 py-3 flex items-center gap-2">
          <i className="fas fa-triangle-exclamation"></i>当前有 {comparable.length} 套关键字段完整候选，超出比较上限（10 套）{pendingText}，请移除部分房源或拆分批次后再比较。
        </div>
      );
    else
      hint = (
        <div className="text-[12px] text-green-700 bg-green-50 border border-green-100 rounded-xl px-4 py-3 flex items-center justify-between">
          <span>
            <i className="fas fa-circle-check mr-1"></i>
            {comparable.length} 套关键字段完整候选可进入比较（3—10 套）{pendingText}
          </span>
          <button onClick={startRecommend} className="text-green-800 font-semibold hover:underline">
            开始筛选 →
          </button>
        </div>
      );
  }

  let list = houses.slice();
  if (hf.filter === 'dropped') list = list.filter((h) => h.status === 'dropped');
  else list = list.filter((h) => h.status === 'active');
  const q = hf.q.trim();
  if (q) list = list.filter((h) => (h.name + h.region + h.notes + h.address).includes(q));
  if (hf.filter === 'whole') list = list.filter((h) => !h.shared);
  if (hf.filter === 'shared') list = list.filter((h) => h.shared);
  if (hf.filter === 'bathroom') list = list.filter((h) => h.bathroom === true);
  if (hf.filter === 'incomplete') list = list.filter((h) => completeness(h) < 70);
  const sorters: Record<string, (a: House, b: House) => number> = {
    rent: (a, b) => (a.rent || 9e9) - (b.rent || 9e9),
    cost: (a, b) => monthlyCost(a).sum - monthlyCost(b).sum,
    commute: (a, b) => (a.commuteMin || 999) - (b.commuteMin || 999),
    completeness: (a, b) => completeness(b) - completeness(a),
  };
  if (sorters[hf.sort]) list.sort(sorters[hf.sort]);

  return (
    <div id="view-houses" className={`${visible ? '' : 'hidden'} flex-1 overflow-y-auto custom-scrollbar`}>
      <div className="max-w-3xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-1">
          <div>
            <h1 className="text-lg font-semibold text-gray-900">本次候选房源</h1>
            <p className="text-xs text-gray-400 mt-1">你自己导入的临时候选，仅用于本次工作台 · 比较范围 3—10 套</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => openImport('batch')}
              className="bg-white border border-gray-200 hover:border-gray-300 text-gray-700 text-xs font-medium rounded-xl px-3.5 py-2.5 transition-colors flex items-center gap-1.5"
            >
              <i className="fas fa-layer-group text-[10px]"></i> 批量导入
            </button>
            <button
              onClick={() => openImport('paste')}
              className="bg-gray-900 hover:bg-gray-700 text-white text-xs font-medium rounded-xl px-4 py-2.5 transition-colors flex items-center gap-1.5"
            >
              <i className="fas fa-plus text-[10px]"></i> 添加房源
            </button>
          </div>
        </div>
        <div id="compareHint" className="my-4">
          {hint}
        </div>
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <div className="relative flex-1 min-w-[180px]">
            <i className="fas fa-magnifying-glass absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-300 text-xs"></i>
            <input
              id="houseSearch"
              value={hf.q}
              onChange={(e) => useStore.setState((s) => ({ hf: { ...s.hf, q: e.target.value } }))}
              className="w-full bg-gray-50 border border-gray-200 rounded-xl pl-9 pr-4 py-2.5 text-[13px] outline-none focus:border-gray-300 focus:bg-white transition-all placeholder:text-gray-400"
              placeholder="搜索名称 / 区域 / 备注…"
            />
          </div>
          <select
            id="houseFilter"
            value={hf.filter}
            onChange={(e) => useStore.setState((s) => ({ hf: { ...s.hf, filter: e.target.value } }))}
            className="bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5 text-[12px] text-gray-600 outline-none focus:border-gray-300"
          >
            <option value="all">全部</option>
            <option value="whole">整租</option>
            <option value="shared">合租</option>
            <option value="bathroom">独立卫浴</option>
            <option value="incomplete">信息不完整</option>
            <option value="dropped">已放弃</option>
          </select>
          <select
            id="houseSort"
            value={hf.sort}
            onChange={(e) => useStore.setState((s) => ({ hf: { ...s.hf, sort: e.target.value } }))}
            className="bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5 text-[12px] text-gray-600 outline-none focus:border-gray-300"
          >
            <option value="default">默认排序</option>
            <option value="rent">月租从低到高</option>
            <option value="cost">月度总成本从低到高</option>
            <option value="commute">通勤从短到长</option>
            <option value="completeness">信息完整度从高到低</option>
          </select>
        </div>
        <div id="houseList" className="space-y-3">
          {list.length === 0 ? (
            <div className="text-center py-16 text-gray-400">
              <i className="fas fa-building-circle-exclamation text-3xl mb-3 text-gray-200"></i>
              <div className="text-[13px]">
                {houses.length ? '没有匹配的房源，试试调整筛选条件' : '还没有候选房源'}
              </div>
              {!houses.length && (
                <button
                  onClick={() => openImport('batch')}
                  className="mt-4 text-xs bg-gray-900 text-white rounded-xl px-4 py-2.5"
                >
                  导入第一批房源
                </button>
              )}
            </div>
          ) : (
            list.map((h) => <HouseCard key={h.id} h={h} />)
          )}
        </div>
      </div>
    </div>
  );
}
