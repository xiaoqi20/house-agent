import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { useStore } from '../store';
import { SOURCE_LABEL } from '../data/demo';
import { completeness, missingFields, monthlyCost, oneTimeCost } from '../lib/calc';
import { getContract, getHouse } from '../lib/selectors';
import { useDrawerTransition } from '../lib/useDrawerTransition';
import { fmt } from '../lib/utils';
import {
  addTodo,
  addVisit,
  bindContractEntry,
  closeHouseDrawer,
  dropHouse,
  restoreHouse,
  saveNotes,
  setTargetHouse,
  showVerificationCard,
} from '../controller';

function FieldRow({
  label,
  value,
  anchor,
  bold,
}: {
  label: string;
  value: ReactNode;
  anchor?: string;
  bold?: boolean;
}) {
  const empty = value === null || value === '' || value === undefined;
  return (
    <div className={`flex justify-between gap-3 py-1.5 ${anchor ? 'relative' : ''}`} id={anchor}>
      <span className="text-gray-400 shrink-0">{label}</span>
      <span className={`text-right ${empty ? 'text-amber-500' : 'text-gray-800'} ${bold ? 'font-semibold' : ''}`}>
        {empty ? '待确认' : value}
      </span>
    </div>
  );
}

function HouseDrawerBody({ houseId }: { houseId: string }) {
  const h = getHouse(houseId);
  const ctx = useStore((s) => s.ctx);
  if (!h) return null;
  const comp = completeness(h);
  const miss = missingFields(h);
  const mc = monthlyCost(h);
  const oc = oneTimeCost(h);
  const boundContract = h.contractId ? getContract(h.contractId) : null;

  return (
    <div className="p-5 space-y-5 text-[13px]">
      {/* 数据状态 */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-[12px] font-semibold text-gray-900">
            <i className="fas fa-chart-pie mr-1.5 text-brand-600"></i>信息完整度
          </h4>
          <span
            className={`text-[11px] font-semibold ${
              comp >= 80 ? 'text-green-600' : comp >= 60 ? 'text-amber-600' : 'text-red-500'
            }`}
          >
            {comp}%
          </span>
        </div>
        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${
              comp >= 80 ? 'bg-green-400' : comp >= 60 ? 'bg-amber-400' : 'bg-red-300'
            }`}
            style={{ width: `${comp}%` }}
          ></div>
        </div>
        {miss.length ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {miss.map((m) => (
              <span key={m} className="text-[10px] text-amber-600 bg-amber-50 border border-amber-100 rounded-full px-2 py-0.5">
                缺 {m}
              </span>
            ))}
          </div>
        ) : (
          <div className="mt-2 text-[11px] text-green-600">
            <i className="fas fa-check mr-1"></i>关键字段均已填写
          </div>
        )}
        <div className="mt-2 text-[10px] text-gray-300">不承诺房源信息长期准确，仅展示来源、完整度与待核实项</div>
      </section>

      {/* 来源与证据 */}
      <section className="bg-gray-50 rounded-2xl p-4">
        <h4 className="text-[12px] font-semibold text-gray-900 mb-2">
          <i className="fas fa-fingerprint mr-1.5 text-brand-600"></i>来源与证据
        </h4>
        <FieldRow label="导入来源" value={SOURCE_LABEL[h.source] || h.source} />
        {h.batch && <FieldRow label="导入批次" value={h.batch} />}
        {h.linkUrl && (
          <div className="text-[11px] text-gray-500 mt-1.5 break-all">
            <i className="fas fa-link mr-1 text-[9px]"></i>
            {h.linkUrl}
          </div>
        )}
        {h.raw && h.raw !== '手动填写，无原始文本' && (
          <div className="mt-2 text-[11px] text-gray-500 leading-relaxed border-t border-gray-100 pt-2">
            <i className="fas fa-quote-left mr-1 text-[9px]"></i>原始内容：
            <mark className="raw">{h.raw}</mark>
          </div>
        )}
      </section>

      {/* 价格 */}
      <section>
        <h4 className="text-[12px] font-semibold text-gray-900 mb-1">
          <i className="fas fa-coins mr-1.5 text-brand-600"></i>价格与费用
        </h4>
        <FieldRow label="月租" value={h.rent ? fmt(h.rent) + ' 元/月' : null} anchor="hd-rent" bold />
        <FieldRow label="押金 / 付款方式" value={h.deposit} anchor="hd-deposit" />
        <FieldRow
          label="物业费"
          value={
            h.propertyFee != null
              ? fmt(h.propertyFee) + ' 元/月' + (h.propertyBear ? '（' + h.propertyBear + '）' : '')
              : null
          }
          anchor="hd-property"
        />
        <FieldRow label="网费" value={h.netFee != null ? fmt(h.netFee) + ' 元/月' : null} />
        <FieldRow
          label="中介费"
          value={h.agencyFee != null ? (h.agencyFee ? fmt(h.agencyFee) + ' 元（一次性）' : '无（房东直租）') : null}
        />
        <div className="mt-2 bg-brand-50/60 border border-brand-100 rounded-xl px-3 py-2.5 text-[12px]">
          <div className="flex justify-between">
            <span className="text-gray-500">月度总成本</span>
            <b className="text-brand-700">
              {mc.unknown.length ? '≈' : ''}
              {fmt(mc.sum)} 元/月
            </b>
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-gray-500">入住一次性支出</span>
            <span className="text-gray-700">
              押金 {fmt(oc.deposit)} 元{oc.agency != null ? ' + 中介费 ' + fmt(oc.agency) + ' 元' : ''}
            </span>
          </div>
          {mc.unknown.length ? (
            <div className="text-[10px] text-amber-600 mt-1.5">
              <i className="fas fa-circle-exclamation mr-1"></i>
              {mc.unknown.join('、')}待确认，实际成本可能更高
            </div>
          ) : null}
        </div>
      </section>

      {/* 居住 */}
      <section>
        <h4 className="text-[12px] font-semibold text-gray-900 mb-1">
          <i className="fas fa-bed mr-1.5 text-brand-600"></i>居住条件
        </h4>
        <FieldRow label="户型" value={h.layout} />
        <FieldRow label="面积" value={h.area != null ? h.area + ' ㎡' : null} />
        <FieldRow label="楼层" value={h.floor} />
        <FieldRow label="朝向" value={h.orientation} />
        <FieldRow label="独立卫浴" value={h.bathroom === true ? '有' : h.bathroom === false ? '无' : null} />
        <FieldRow label="采光" value={h.lighting} />
        <FieldRow label="家具家电" value={h.furniture} />
      </section>

      {/* 位置 */}
      <section>
        <h4 className="text-[12px] font-semibold text-gray-900 mb-1">
          <i className="fas fa-location-dot mr-1.5 text-brand-600"></i>位置与通勤
        </h4>
        <FieldRow label="区域" value={h.region} />
        <FieldRow label="通勤" value={h.commuteMin ? h.commuteMode + ' ' + h.commuteMin + ' 分钟' : null} />
        <FieldRow label="最近地铁" value={h.metro} />
      </section>

      {/* 约束 */}
      <section>
        <h4 className="text-[12px] font-semibold text-gray-900 mb-1">
          <i className="fas fa-list-check mr-1.5 text-brand-600"></i>关键约束
        </h4>
        <FieldRow label="宠物" value={h.pet} anchor="hd-pet" />
        <FieldRow label="合租" value={h.shared ? '合租' : '整租'} />
        <FieldRow label="可入住时间" value={h.available} anchor="hd-available" />
        <FieldRow label="入住人数" value={h.maxPeople ? '限 ' + h.maxPeople + ' 人' : null} />
      </section>

      {/* 待核实项 */}
      <section>
        <h4 className="text-[12px] font-semibold text-gray-900 mb-2">
          <i className="fas fa-circle-question mr-1.5 text-amber-500"></i>待核实项（{h.verify.length}）
        </h4>
        {h.verify.length ? (
          h.verify.map((v, i) => (
            <div className="flex items-start gap-2 text-[12px] text-gray-600 py-1" key={i}>
              <i className="fas fa-circle-dot text-amber-400 text-[8px] mt-1.5"></i>
              {v}
            </div>
          ))
        ) : (
          <div className="text-[12px] text-gray-300">暂无</div>
        )}
      </section>

      {/* 待确认问题 */}
      <section>
        <h4 className="text-[12px] font-semibold text-gray-900 mb-2">
          <i className="fas fa-clipboard-question mr-1.5 text-brand-600"></i>看房 / 联系房东要问的问题（{h.todos.length}）
        </h4>
        {h.todos.length ? (
          h.todos.map((t, i) => (
            <label className="flex items-start gap-2 text-[12px] text-gray-600 py-1 cursor-pointer" key={i}>
              <input type="checkbox" className="mt-1 w-3.5 h-3.5 rounded border-gray-300 text-brand-500" /> {t}
            </label>
          ))
        ) : (
          <div className="text-[12px] text-gray-300">暂无</div>
        )}
        <div className="flex gap-2 mt-2">
          <input
            id="newTodo"
            className="flex-1 bg-gray-50 border border-gray-200 rounded-xl px-3 py-2 text-[12px] outline-none focus:border-gray-300 focus:bg-white"
            placeholder="补充一个待确认问题…"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                addTodo(h.id, (e.target as HTMLInputElement).value);
                (e.target as HTMLInputElement).value = '';
              }
            }}
          />
          <button
            onClick={() => {
              const el = document.getElementById('newTodo') as HTMLInputElement | null;
              if (el?.value) {
                addTodo(h.id, el.value);
                el.value = '';
              }
            }}
            className="text-xs bg-gray-900 text-white rounded-xl px-3"
          >
            添加
          </button>
        </div>
      </section>

      {/* 备注与看房记录 */}
      <section>
        <h4 className="text-[12px] font-semibold text-gray-900 mb-2">
          <i className="fas fa-note-sticky mr-1.5 text-brand-600"></i>我的备注
        </h4>
        <textarea
          id="houseNotes"
          rows={2}
          defaultValue={h.notes}
          className="w-full bg-gray-50 border border-gray-200 rounded-xl px-3 py-2 text-[12px] outline-none focus:border-gray-300 focus:bg-white custom-scrollbar"
          placeholder="记录看房感受、房东承诺…"
        ></textarea>
        <div className="flex justify-end mt-1.5">
          <button
            onClick={() => {
              const el = document.getElementById('houseNotes') as HTMLTextAreaElement | null;
              saveNotes(h.id, el?.value || '');
            }}
            className="text-[11px] text-brand-600 hover:text-brand-700 font-medium"
          >
            保存备注
          </button>
        </div>
        <h4 className="text-[12px] font-semibold text-gray-900 mt-4 mb-2">
          <i className="fas fa-shoe-prints mr-1.5 text-brand-600"></i>看房记录（{h.visits.length}）
        </h4>
        {h.visits.length ? (
          h.visits.map((v, i) => (
            <div className="text-[12px] text-gray-600 bg-gray-50 rounded-xl px-3 py-2 mb-1.5" key={i}>
              <span className="text-gray-400 mr-2">{v.time}</span>
              {v.text}
            </div>
          ))
        ) : (
          <div className="text-[12px] text-gray-300 mb-1.5">还没有看房记录</div>
        )}
        <div className="flex gap-2 mt-1">
          <input
            id="newVisit"
            className="flex-1 bg-gray-50 border border-gray-200 rounded-xl px-3 py-2 text-[12px] outline-none focus:border-gray-300 focus:bg-white"
            placeholder="如：9/10 晚看房，南向采光确认，有异味…"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                addVisit(h.id, (e.target as HTMLInputElement).value);
                (e.target as HTMLInputElement).value = '';
              }
            }}
          />
          <button
            onClick={() => {
              const el = document.getElementById('newVisit') as HTMLInputElement | null;
              if (el?.value) {
                addVisit(h.id, el.value);
                el.value = '';
              }
            }}
            className="text-xs bg-gray-900 text-white rounded-xl px-3"
          >
            记录
          </button>
        </div>
      </section>

      {/* 关联合同 */}
      <section>
        <h4 className="text-[12px] font-semibold text-gray-900 mb-2">
          <i className="fas fa-file-contract mr-1.5 text-brand-600"></i>关联合同
        </h4>
        {boundContract ? (
          <div className="border border-gray-200 rounded-2xl p-3.5 flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-red-50 text-red-500 border border-red-100 flex items-center justify-center shrink-0">
              <i className="fas fa-file-pdf"></i>
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[12px] font-medium text-gray-900 truncate">{boundContract.name}</div>
              <div className="text-[10px] text-gray-400">
                {boundContract.no} · 已绑定 {h.no}
              </div>
            </div>
            <button
              onClick={() => showVerificationCard(h.id)}
              className="text-xs text-brand-600 hover:bg-brand-50 rounded-lg px-2.5 py-1.5"
            >
              查看核验
            </button>
          </div>
        ) : (
          <div className="text-[12px] text-gray-400 bg-gray-50 rounded-xl px-3 py-2.5">
            尚未绑定合同。绑定后可将房源承诺与合同条款逐项核验。
          </div>
        )}
      </section>

      {/* 操作 */}
      <section className="flex flex-wrap gap-2 pb-4">
        {ctx.houseId !== h.id ? (
          <button
            onClick={() => setTargetHouse(h.id)}
            className="flex-1 min-w-[120px] bg-gray-900 hover:bg-gray-700 text-white rounded-xl py-2.5 text-xs font-medium transition-colors"
          >
            <i className="fas fa-crosshairs mr-1"></i>设为目标房源
          </button>
        ) : (
          <div className="flex-1 min-w-[120px] text-center text-xs text-brand-600 bg-brand-50 border border-brand-100 rounded-xl py-2.5 font-medium">
            <i className="fas fa-check mr-1"></i>当前目标房源
          </div>
        )}
        <button
          onClick={() => bindContractEntry(h.id)}
          className="flex-1 min-w-[120px] bg-white border border-gray-200 hover:border-brand-300 text-gray-700 rounded-xl py-2.5 text-xs font-medium transition-colors"
        >
          <i className="fas fa-file-contract mr-1"></i>
          {h.contractId ? '查看合同核验' : '绑定合同'}
        </button>
        {h.status === 'active' ? (
          <button
            onClick={() => dropHouse(h.id)}
            className="bg-white border border-gray-200 hover:bg-gray-50 text-gray-500 rounded-xl py-2.5 px-3.5 text-xs transition-colors"
          >
            标记放弃
          </button>
        ) : (
          <button
            onClick={() => restoreHouse(h.id)}
            className="bg-white border border-gray-200 hover:bg-gray-50 text-gray-500 rounded-xl py-2.5 px-3.5 text-xs transition-colors"
          >
            恢复候选
          </button>
        )}
      </section>
    </div>
  );
}

export function HouseDrawer() {
  const { open, houseId, anchor } = useStore((s) => s.houseDrawer);
  useStore((s) => s.houses); // 房源数据变化时刷新抽屉
  const { mounted, shown } = useDrawerTransition(open);
  const h = houseId ? getHouse(houseId) : null;

  if (!mounted || !h) return null;

  return (
    <>
      <div
        id="houseOverlay"
        className={`${shown ? '' : 'hidden'} fixed inset-0 bg-black/20 z-30`}
        onClick={closeHouseDrawer}
      ></div>
      <aside
        id="houseDrawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="houseDrawerTitle"
        aria-hidden={!shown}
        inert={!shown}
        className={`${
          shown ? '' : 'translate-x-full'
        } fixed inset-y-0 right-0 w-full max-w-lg bg-white shadow-2xl z-40 transform transition-transform duration-300 flex flex-col`}
      >
        <div className="h-16 flex items-center justify-between px-5 border-b border-gray-100 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-lg bg-emerald-50 flex items-center justify-center text-emerald-600 border border-emerald-100 shrink-0">
              <i className="fas fa-building"></i>
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-gray-900 truncate" id="houseDrawerTitle">
                {h.name}
              </div>
              <div className="text-[11px] text-gray-500" id="houseDrawerMeta">
                {h.no} · {SOURCE_LABEL[h.source] || h.source}
                {h.batch ? ' · 批次 ' + h.batch : ''}
              </div>
            </div>
          </div>
          <button
            onClick={closeHouseDrawer}
            aria-label="关闭房源详情抽屉"
            className="w-8 h-8 rounded-lg hover:bg-gray-100 text-gray-400 flex items-center justify-center shrink-0"
          >
            <i className="fas fa-times"></i>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar" id="houseDrawerBody">
          <HouseDrawerBody
            key={`${h.id}:${h.notes}:${h.visits.length}:${h.todos.length}:${h.status}`}
            houseId={h.id}
          />
        </div>
      </aside>
      {/* 打开后定位到指定字段（核验项 → 房源字段） */}
      {shown && anchor ? <ScrollToAnchor key={`${h.id}:${anchor}`} anchor={anchor} /> : null}
    </>
  );
}

function ScrollToAnchor({ anchor }: { anchor: string }) {
  useEffect(() => {
    const timer = setTimeout(() => {
      document.getElementById(anchor)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 350);
    return () => clearTimeout(timer);
  }, [anchor]);
  return null;
}
