import { useStore } from '../../store';
import type { House, Preferences, RecView, RecommendSnapshot, RecommendationResult } from '../../types';
import type { ExplanationDto, RankItemDto } from '../../api/types';
import { getDemoStore, SOURCE_LABEL } from '../../data/demo';
import {
  completeness,
  comparisonMissingFields,
  missingFields,
  monthlyCost,
  oneTimeCost,
} from '../../lib/calc';
import { hardCheck, softScore } from '../../lib/recommend';
import { fmt } from '../../lib/utils';
import {
  bindContractEntry,
  dropHouse,
  openHouseDrawer,
  openPrefs,
  recommendFlow,
  send,
  setRecView,
  setTargetHouse,
} from '../../controller';

const REC_STATUS: Record<'top' | 'alt' | 'no', [string, string]> = {
  top: ['优先考虑', 'bg-green-50 text-green-600 border-green-100'],
  alt: ['可作为备选', 'bg-sky-50 text-brand-600 border-brand-100'],
  no: ['不建议', 'bg-red-50 text-red-500 border-red-100'],
};

function RecHouseCard({
  h,
  status,
  readOnly,
  prefs,
}: {
  h: House;
  status: 'top' | 'alt' | 'no';
  readOnly?: boolean;
  prefs: Preferences;
}) {
  const [stLabel, stCls] = REC_STATUS[status];
  const comp = completeness(h);
  const miss = missingFields(h);
  const mc = monthlyCost(h);
  const oc = oneTimeCost(h);
  const soft = softScore(h, prefs);
  const reasons: string[] = [];
  if (prefs.budget != null && h.rent != null && h.rent <= prefs.budget) reasons.push(`月租 ${fmt(h.rent)} 在预算内`);
  if (prefs.commute != null && h.commuteMin != null && h.commuteMin <= prefs.commute)
    reasons.push(`通勤 ${h.commuteMin} 分钟达标`);
  if (prefs.needBathroom && h.bathroom === true) reasons.push('有独立卫浴');
  soft.hits.forEach((x) => reasons.push('符合软偏好：' + x));
  if (!reasons.length) reasons.push('满足全部硬约束');
  const tradeoffs: string[] = [];
  if (prefs.budget != null && h.rent != null && h.rent > prefs.budget * 0.9) tradeoffs.push('租金接近预算上限，议价空间小');
  if (prefs.commute != null && h.commuteMin != null && h.commuteMin > prefs.commute * 0.85)
    tradeoffs.push('通勤接近上限');
  soft.miss.forEach((x) => tradeoffs.push('未满足软偏好：' + x));
  if (h.shared) tradeoffs.push('合租隐私与公区规则需确认');
  const risks: string[] = [];
  miss.forEach((m) => risks.push(m + ' 缺失'));
  h.verify.slice(0, 2).forEach((v) => risks.push(v));
  const todosQ = h.todos.length ? h.todos : ['确认费用明细与承担方', '确认可入住时间'];

  return (
    <div className="border-t border-gray-100 px-4 py-4">
      <div className="flex items-center gap-2 flex-wrap mb-2.5">
        <span className="text-[10px] font-bold text-gray-400 bg-gray-100 rounded px-1.5 py-0.5">{h.no}</span>
        <span className="text-[13px] font-semibold text-gray-900">{h.name}</span>
        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${stCls}`}>{stLabel}</span>
        <span className="text-[10px] text-gray-400">
          {SOURCE_LABEL[h.source] || h.source} · 完整度 {comp}%{comp < 70 ? ' · 部分信息缺失' : ''}
        </span>
      </div>
      <div className="grid sm:grid-cols-2 gap-x-5 gap-y-2.5 text-[12px]">
        <div>
          <div className="text-[11px] font-semibold text-green-600 mb-1">
            <i className="fas fa-thumbs-up mr-1"></i>推荐理由
          </div>
          {reasons.map((r, i) => (
            <div className="text-gray-600 py-0.5" key={i}>
              · {r}
            </div>
          ))}
        </div>
        <div>
          <div className="text-[11px] font-semibold text-amber-600 mb-1">
            <i className="fas fa-scale-unbalanced mr-1"></i>不足与取舍
          </div>
          {tradeoffs.length ? (
            tradeoffs.map((r, i) => (
              <div className="text-gray-600 py-0.5" key={i}>
                · {r}
              </div>
            ))
          ) : (
            <div className="text-gray-400 py-0.5">· 暂无明显短板</div>
          )}
        </div>
        <div>
          <div className="text-[11px] font-semibold text-brand-600 mb-1">
            <i className="fas fa-coins mr-1"></i>真实成本
          </div>
          <div className="text-gray-600 py-0.5">
            · 月度总成本 {mc.unknown.length ? '≈' : ''}
            <b>{fmt(mc.sum)}</b>
            {` 元（月租 ${h.rent ? fmt(h.rent) : '待定'}${
              h.propertyFee != null ? ' + 物业 ' + fmt(h.propertyFee) : ''
            }${h.netFee != null && h.netFee ? ' + 网费 ' + fmt(h.netFee) : ''}）`}
          </div>
          <div className="text-gray-600 py-0.5">
            {`· 一次性支出：押金 ${fmt(oc.deposit)} 元（${oc.label || '待确认'}）${
              oc.agency != null ? '，中介费 ' + (oc.agency ? fmt(oc.agency) + ' 元' : '0') : ''
            }`}
          </div>
          {mc.unknown.length > 0 && (
            <div className="text-amber-500 py-0.5">· {mc.unknown.join('、')}待确认，成本可能上浮</div>
          )}
        </div>
        <div>
          <div className="text-[11px] font-semibold text-red-400 mb-1">
            <i className="fas fa-triangle-exclamation mr-1"></i>信息风险
          </div>
          {risks.length ? (
            risks.map((r, i) => (
              <div className="text-gray-600 py-0.5" key={i}>
                · {r}
              </div>
            ))
          ) : (
            <div className="text-gray-400 py-0.5">· 关键信息完整</div>
          )}
        </div>
      </div>
      <div className="mt-2.5 bg-amber-50/50 border border-amber-100 rounded-xl px-3 py-2">
        <span className="text-[11px] font-semibold text-amber-600 mr-1.5">
          <i className="fas fa-clipboard-question mr-1"></i>待确认
        </span>{' '}
        <span className="text-[11px] text-amber-700">{todosQ.join('；')}</span>
      </div>
      {readOnly ? (
        <div className="mt-2.5 text-[11px] text-amber-600 bg-amber-50/60 border border-amber-100 rounded-xl px-3 py-2">
          <i className="fas fa-flask mr-1"></i>历史示例快照，仅供查看
        </div>
      ) : (
        <div className="mt-2.5 flex flex-wrap gap-2">
          <button
            onClick={() => openHouseDrawer(h.id)}
            className="text-[11px] bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1.5 transition-colors"
          >
            查看详情
          </button>
          <button
            onClick={() => setTargetHouse(h.id)}
            className="text-[11px] bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1.5 transition-colors"
          >
            设为目标房源
          </button>
          <button
            onClick={() => bindContractEntry(h.id)}
            className="text-[11px] bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1.5 transition-colors"
          >
            {h.contractId ? '查看合同核验' : '绑定合同'}
          </button>
          <button
            onClick={() => dropHouse(h.id)}
            className="text-[11px] bg-white border border-gray-200 hover:bg-gray-50 text-gray-400 rounded-full px-3 py-1.5 transition-colors"
          >
            标记放弃
          </button>
        </div>
      )}
    </div>
  );
}

function FailRow({ h, violations }: { h: House; violations: string[] }) {
  return (
    <div className="px-4 py-2.5 border-t border-gray-50 flex items-start gap-3 opacity-80">
      <span className="text-[10px] font-bold text-gray-400 bg-gray-100 rounded px-1.5 py-0.5 mt-0.5 shrink-0">
        {h.no}
      </span>
      <div className="flex-1 min-w-0">
        <span className="text-[12px] font-medium text-gray-700">{h.name}</span>
        <div className="text-[11px] text-red-400 mt-0.5">{violations.join('；')}</div>
      </div>
      <button
        onClick={() => openHouseDrawer(h.id)}
        className="text-[11px] text-gray-400 hover:text-gray-600 shrink-0"
      >
        详情
      </button>
    </div>
  );
}

function DemoRecommendCard({ prefs }: { prefs: Preferences }) {
  const demoList = getDemoStore().houses;
  const pool = demoList.filter((h) => !(h.shared && !prefs.allowShared));
  const rows = pool.map((h) => ({ h, violations: hardCheck(h, prefs) }));
  const pass = rows
    .filter((r) => !r.violations.length)
    .sort(
      (a, b) => softScore(b.h, prefs).score - softScore(a.h, prefs).score || monthlyCost(a.h).sum - monthlyCost(b.h).sum,
    );
  const fail = rows.filter((r) => r.violations.length);

  return (
    <>
      <div className="text-[14px] text-gray-800 mb-2.5 leading-relaxed">
        基于你的硬约束与软偏好，对 <b>{demoList.length} 套候选</b>的推荐如下。每套都给出理由、取舍、真实成本和待确认项，不输出唯一排名：
      </div>
      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
        <div className="px-4 py-3 flex items-center justify-between bg-gray-50/80 border-b border-gray-100 flex-wrap gap-2">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-gray-900">
            <i className="fas fa-table-list text-brand-600"></i> 推荐结果{' '}
            <span className="text-[10px] bg-amber-100 text-amber-700 border border-amber-200 rounded px-1.5 py-0.5 ml-1">
              历史示例快照
            </span>
          </div>
        </div>
        <div>
          <div className="px-4 pt-3 text-[11px] text-gray-400">当前视角：综合匹配（软偏好 + 成本）</div>
          {pass.map((r, i) => (
            <RecHouseCard key={r.h.id} h={r.h} status={i === 0 ? 'top' : 'alt'} readOnly prefs={prefs} />
          ))}
          {fail.length > 0 && (
            <div className="border-t border-gray-100">
              <div className="px-4 py-2.5 text-[11px] font-semibold text-red-400 bg-red-50/50">
                <i className="fas fa-ban mr-1"></i>硬约束不满足（{fail.length} 套）
              </div>
              {fail.map((r) => (
                <FailRow key={r.h.id} h={r.h} violations={r.violations} />
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export type RecommendCardProps =
  | { variant: 'live'; snapshot: RecommendSnapshot }
  | { variant: 'demo'; demoPrefs: Preferences }
  | { variant: 'server'; data: RecommendationResult };

const VERDICT_STATUS: Record<RankItemDto['verdict'], 'top' | 'alt' | 'no'> = {
  优先考虑: 'top',
  可作为备选: 'alt',
  不建议: 'no',
};

/** explanation.next → 可点操作（服务端只给动作名称，操作在前端） */
function nextAction(label: string, h: House): () => void {
  if (label.includes('查看')) return () => openHouseDrawer(h.id);
  if (label.includes('合同') || label.includes('核验')) return () => bindContractEntry(h.id);
  if (label.includes('目标')) return () => setTargetHouse(h.id);
  if (label.includes('放弃') || label.includes('移除')) return () => dropHouse(h.id);
  return () => send(label);
}

function Bullets({ items, empty }: { items: string[]; empty: string }) {
  if (!items.length) return <div className="text-gray-400 py-0.5">· {empty}</div>;
  return (
    <>
      {items.map((r, i) => (
        <div className="text-gray-600 py-0.5" key={i}>
          · {r}
        </div>
      ))}
    </>
  );
}

/** 服务端单套推荐卡：排序/成本/硬约束来自 domain，理由/取舍/风险来自 explanation */
function ServerHouseCard({
  h,
  item,
  explanation,
}: {
  h: House;
  item: RankItemDto;
  explanation?: ExplanationDto;
}) {
  const [stLabel, stCls] = REC_STATUS[VERDICT_STATUS[item.verdict] ?? 'alt'];
  const why = explanation?.why ?? [];
  const tradeoffs = explanation?.tradeoffs ?? [];
  const risks = [...(explanation?.risks ?? []), ...item.hard_violations.map((v) => `硬约束不满足：${v}`)];
  const todos = explanation?.todos ?? [];
  const next = explanation?.next ?? [];
  return (
    <div className="border-t border-gray-100 px-4 py-4">
      <div className="flex items-center gap-2 flex-wrap mb-2.5">
        <span className="text-[10px] font-bold text-gray-400 bg-gray-100 rounded px-1.5 py-0.5">{h.no}</span>
        <span className="text-[13px] font-semibold text-gray-900">{h.name}</span>
        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${stCls}`}>
          #{item.rank} {stLabel}
        </span>
        <span className="text-[10px] text-gray-400">{SOURCE_LABEL[h.source] || h.source}</span>
        {!item.comparable && (
          <span className="text-[10px] text-amber-600 bg-amber-50 border border-amber-100 rounded-full px-2 py-0.5">
            关键字段不完整，未参与排序
          </span>
        )}
      </div>
      {item.tie_break_note && <div className="text-[11px] text-gray-400 mb-2">{item.tie_break_note}</div>}
      <div className="grid sm:grid-cols-2 gap-x-5 gap-y-2.5 text-[12px]">
        <div>
          <div className="text-[11px] font-semibold text-green-600 mb-1">
            <i className="fas fa-thumbs-up mr-1"></i>推荐理由
          </div>
          <Bullets items={why} empty="暂无可列出的推荐理由" />
        </div>
        <div>
          <div className="text-[11px] font-semibold text-amber-600 mb-1">
            <i className="fas fa-scale-unbalanced mr-1"></i>不足与取舍
          </div>
          <Bullets items={tradeoffs} empty="暂无明显短板" />
        </div>
        <div>
          <div className="text-[11px] font-semibold text-brand-600 mb-1">
            <i className="fas fa-coins mr-1"></i>真实成本
          </div>
          <div className="text-gray-600 py-0.5">
            · 月度总成本 {item.monthly_cost_unknown?.length ? '≈' : ''}
            <b>{fmt(item.monthly_cost)}</b> 元
          </div>
          <div className="text-gray-600 py-0.5">
            · 一次性支出 {fmt(item.one_time_cost)} 元
            {item.one_time_label ? `（${item.one_time_label}）` : ''}
          </div>
          {(item.soft_hits.length > 0 || item.soft_miss.length > 0) && (
            <div className="text-gray-600 py-0.5">
              · 软偏好命中：{item.soft_hits.length ? item.soft_hits.join('、') : '无'}
              {item.soft_miss.length ? `；未命中：${item.soft_miss.join('、')}` : ''}
            </div>
          )}
        </div>
        <div>
          <div className="text-[11px] font-semibold text-red-400 mb-1">
            <i className="fas fa-triangle-exclamation mr-1"></i>信息风险
          </div>
          <Bullets items={risks} empty="关键信息完整" />
        </div>
      </div>
      <div className="mt-2.5 bg-amber-50/50 border border-amber-100 rounded-xl px-3 py-2">
        <span className="text-[11px] font-semibold text-amber-600 mr-1.5">
          <i className="fas fa-clipboard-question mr-1"></i>待确认
        </span>{' '}
        <span className="text-[11px] text-amber-700">{todos.length ? todos.join('；') : '暂无待确认项'}</span>
      </div>
      <div className="mt-2.5 flex flex-wrap gap-2">
        {(next.length ? next : ['查看详情']).map((label) => (
          <button
            key={label}
            onClick={nextAction(label, h)}
            className="text-[11px] bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1.5 transition-colors"
          >
            {label}
          </button>
        ))}
        <button
          onClick={() => setTargetHouse(h.id)}
          className="text-[11px] bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1.5 transition-colors"
        >
          设为目标房源
        </button>
        <button
          onClick={() => bindContractEntry(h.id)}
          className="text-[11px] bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1.5 transition-colors"
        >
          {h.contractId ? '查看合同核验' : '绑定合同'}
        </button>
        <button
          onClick={() => dropHouse(h.id)}
          className="text-[11px] bg-white border border-gray-200 hover:bg-gray-50 text-gray-400 rounded-full px-3 py-1.5 transition-colors"
        >
          标记放弃
        </button>
      </div>
    </div>
  );
}

/** 服务端三视图推荐卡（契约 §4.5：三视图排序 + explanation + about） */
function ServerRecommendCard({ data }: { data: RecommendationResult }) {
  const recView = useStore((s) => s.recView);
  const prefs = useStore((s) => s.prefs);
  const byId = new Map(data.houses.map((h) => [h.id, h]));
  const view = data.views[recView] ?? { order: [], items: {} };
  const order = view.order.length ? view.order : Object.keys(view.items);
  const rows = order
    .map((id) => ({ id, item: view.items[id], h: byId.get(id) }))
    .filter((row): row is { id: string; item: RankItemDto; h: House } => Boolean(row.item && row.h));
  const comparable = rows.filter((r) => r.item.comparable);
  const pending = rows.filter((r) => !r.item.comparable);
  const viewLabel = {
    mix: '综合匹配（硬约束 + 软偏好 + 成本）',
    budget: '按月度总成本从低到高',
    commute: '按通勤从短到长',
  }[recView];

  return (
    <>
      <div className="text-[14px] text-gray-800 mb-2.5 leading-relaxed">
        基于你的硬约束与软偏好，对 <b>{data.houses.length} 套候选</b>的推荐如下（第 {data.prefsVersion} 版偏好）。每套都给出理由、取舍、真实成本和待确认项，不输出唯一排名：
      </div>
      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
        <div className="px-4 py-3 flex items-center justify-between bg-gray-50/80 border-b border-gray-100 flex-wrap gap-2">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-gray-900">
            <i className="fas fa-table-list text-brand-600"></i> 推荐结果
            <span className="text-[10px] font-normal text-gray-400">
              预算 ≤ {prefs.budget ? fmt(prefs.budget) : '不限'} · 通勤 ≤{' '}
              {prefs.commute ? prefs.commute + '分钟' : '不限'} · {prefs.needBathroom ? '须独卫' : '不限独卫'}
            </span>
          </div>
          <div className="flex gap-1 bg-gray-100 rounded-full p-0.5">
            {(
              [
                ['mix', '综合匹配'],
                ['budget', '按预算'],
                ['commute', '按通勤'],
              ] as Array<[RecView, string]>
            ).map(([v, l]) => (
              <button
                key={v}
                onClick={() => setRecView(v)}
                className={`text-[11px] rounded-full px-3 py-1 transition-colors ${
                  recView === v ? 'bg-white shadow-sm text-gray-900 font-medium' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
        <div id="recBody">
          <div className="px-4 pt-3 text-[11px] text-gray-400">当前视角：{viewLabel}</div>
          {data.about.window && (
            <div className="px-4 pt-2 text-[11px] text-gray-500">{data.about.window.message}</div>
          )}
          {comparable.length === 0 ? (
            <div className="px-6 py-10 text-center">
              <i className="fas fa-filter-circle-xmark text-3xl text-gray-200 mb-3"></i>
              <div className="text-[13px] font-medium text-gray-700">当前硬约束下没有可推荐的房源</div>
              <div className="text-[12px] text-gray-400 mt-1.5">可以放宽预算 / 通勤上限，或允许合租后重新推荐</div>
              <button onClick={openPrefs} className="mt-4 text-xs bg-gray-900 text-white rounded-xl px-4 py-2.5">
                调整偏好
              </button>
            </div>
          ) : (
            comparable.map((r) => (
              <ServerHouseCard key={r.id} h={r.h} item={r.item} explanation={data.explanation[r.id]} />
            ))
          )}
          {pending.length > 0 && (
            <div className="border-t border-gray-100">
              <div className="px-4 py-2.5 text-[11px] font-semibold text-amber-600 bg-amber-50/60">
                <i className="fas fa-clipboard-question mr-1"></i>关键字段不完整（{pending.length} 套），未参与排序
              </div>
              {pending.map((r) => (
                <ServerHouseCard key={r.id} h={r.h} item={r.item} explanation={data.explanation[r.id]} />
              ))}
            </div>
          )}
        </div>
        <div className="px-4 py-3 border-t border-gray-100 text-[11px] text-gray-400 space-y-0.5">
          {data.about.hardRules.map((rule) => (
            <div key={rule}>硬约束：{rule}</div>
          ))}
          <div>软偏好：{data.about.softRules.join('·')}</div>
          {data.about.missing.length > 0 && <div>缺失字段：{data.about.missing.join('；')}</div>}
        </div>
        <div className="px-4 py-3 border-t border-gray-100 flex flex-wrap gap-2">
          <button
            onClick={openPrefs}
            className="text-xs bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1.5 transition-colors"
          >
            <i className="fas fa-sliders mr-1"></i>修改偏好重新推荐
          </button>
          <button
            onClick={() => recommendFlow(null, true)}
            className="text-xs bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1.5 transition-colors"
          >
            <i className="fas fa-rotate-right mr-1"></i>按当前偏好重新生成
          </button>
        </div>
      </div>
    </>
  );
}

export function RecommendCard(props: RecommendCardProps) {
  const recView = useStore((s) => s.recView);

  if (props.variant === 'server') return <ServerRecommendCard data={props.data} />;
  if (props.variant === 'demo') return <DemoRecommendCard prefs={props.demoPrefs} />;

  const { houses: allHouses, prefs } = props.snapshot;
  const all = allHouses.filter((h) => h.status === 'active');
  const candidates = all.filter((h) => comparisonMissingFields(h, prefs).length === 0);
  const pending = all.filter((h) => comparisonMissingFields(h, prefs).length > 0);
  const sharedOut = candidates.filter((h) => h.shared && !prefs.allowShared);
  const pool = candidates.filter((h) => !(h.shared && !prefs.allowShared));
  const rows = pool.map((h) => ({ h, violations: hardCheck(h, prefs) }));
  const pass = rows.filter((r) => !r.violations.length);
  const fail = rows.filter((r) => r.violations.length);
  const sorters: Record<RecView, (a: { h: House }, b: { h: House }) => number> = {
    budget: (a, b) => {
      if (a.h.rent == null && b.h.rent == null) return 0;
      if (a.h.rent == null) return 1;
      if (b.h.rent == null) return -1;
      return monthlyCost(a.h).sum - monthlyCost(b.h).sum;
    },
    commute: (a, b) => (a.h.commuteMin || 999) - (b.h.commuteMin || 999),
    mix: (a, b) =>
      softScore(b.h, prefs).score - softScore(a.h, prefs).score ||
      monthlyCost(a.h).sum - monthlyCost(b.h).sum,
  };
  pass.sort(sorters[recView]);
  const viewLabel = {
    mix: '综合匹配（软偏好 + 成本）',
    budget: '按月度总成本从低到高',
    commute: '按通勤从短到长',
  }[recView];

  return (
    <>
      <div className="text-[14px] text-gray-800 mb-2.5 leading-relaxed">
        基于你的硬约束与软偏好，对 <b>{candidates.length} 套关键字段完整候选</b>的推荐如下。每套都给出理由、取舍、真实成本和待确认项，不输出唯一排名：
      </div>
      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
        <div className="px-4 py-3 flex items-center justify-between bg-gray-50/80 border-b border-gray-100 flex-wrap gap-2">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-gray-900">
            <i className="fas fa-table-list text-brand-600"></i> 推荐结果
            <span className="text-[10px] font-normal text-gray-400">
              预算 ≤ {prefs.budget ? fmt(prefs.budget) : '不限'} · 通勤 ≤{' '}
              {prefs.commute ? prefs.commute + '分钟' : '不限'} · {prefs.needBathroom ? '须独卫' : '不限独卫'}
            </span>
          </div>
          <div className="flex gap-1 bg-gray-100 rounded-full p-0.5">
            {(
              [
                ['mix', '综合匹配'],
                ['budget', '按预算'],
                ['commute', '按通勤'],
              ] as Array<[RecView, string]>
            ).map(([v, l]) => (
              <button
                key={v}
                onClick={() => setRecView(v)}
                className={`text-[11px] rounded-full px-3 py-1 transition-colors ${
                  recView === v ? 'bg-white shadow-sm text-gray-900 font-medium' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
        <div id="recBody">
          <div className="px-4 pt-3 text-[11px] text-gray-400">当前视角：{viewLabel}</div>
          {pass.length === 0 ? (
            <div className="px-6 py-10 text-center">
              <i className="fas fa-filter-circle-xmark text-3xl text-gray-200 mb-3"></i>
              <div className="text-[13px] font-medium text-gray-700">当前硬约束下没有可推荐的房源</div>
              <div className="text-[12px] text-gray-400 mt-1.5">可以放宽预算 / 通勤上限，或允许合租后重新推荐</div>
              <button onClick={openPrefs} className="mt-4 text-xs bg-gray-900 text-white rounded-xl px-4 py-2.5">
                调整偏好
              </button>
            </div>
          ) : (
            pass.map((r, i) => (
              <RecHouseCard key={r.h.id} h={r.h} status={i === 0 ? 'top' : 'alt'} prefs={prefs} />
            ))
          )}
          {fail.length > 0 && (
            <div className="border-t border-gray-100">
              <div className="px-4 py-2.5 text-[11px] font-semibold text-red-400 bg-red-50/50">
                <i className="fas fa-ban mr-1"></i>硬约束不满足（{fail.length} 套）
              </div>
              {fail.map((r) => (
                <FailRow key={r.h.id} h={r.h} violations={r.violations} />
              ))}
            </div>
          )}
          {sharedOut.length > 0 && (
            <div className="px-4 py-2.5 border-t border-gray-100 bg-purple-50/40 text-[11px] text-purple-600 flex items-center justify-between">
              <span>
                <i className="fas fa-user-group mr-1"></i>
                {sharedOut.length} 套合租房源未纳入（当前偏好不接受合租）
              </span>
              <button
                onClick={() => {
                  useStore.setState({ prefs: { ...useStore.getState().prefs, allowShared: true } });
                  recommendFlow(null, true);
                }}
                className="font-semibold hover:underline"
              >
                允许合租并重新推荐 →
              </button>
            </div>
          )}
          {pending.length > 0 && (
            <div className="border-t border-gray-100">
              <div className="px-4 py-2.5 text-[11px] font-semibold text-amber-600 bg-amber-50/60">
                <i className="fas fa-clipboard-question mr-1"></i>待完善候选（{pending.length} 套），未纳入本次推荐比较
              </div>
              {pending.map((h) => (
                <div className="px-4 py-2.5 border-t border-gray-50 flex items-start gap-3" key={h.id}>
                  <span className="text-[10px] font-bold text-gray-400 bg-gray-100 rounded px-1.5 py-0.5 mt-0.5 shrink-0">
                    {h.no}
                  </span>
                  <div className="flex-1 min-w-0">
                    <span className="text-[12px] font-medium text-gray-700">{h.name}</span>
                    <div className="text-[11px] text-amber-600 mt-0.5">
                      缺少：{comparisonMissingFields(h, prefs).join('、')}
                    </div>
                  </div>
                  <button
                    onClick={() => openHouseDrawer(h.id)}
                    className="text-[11px] text-gray-400 hover:text-gray-600 shrink-0"
                  >
                    补充字段
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="px-4 py-3 border-t border-gray-100 flex flex-wrap gap-2">
          <button
            onClick={openPrefs}
            className="text-xs bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1.5 transition-colors"
          >
            <i className="fas fa-sliders mr-1"></i>修改偏好重新推荐
          </button>
          <button
            onClick={() =>
              send(
                `预算 ${prefs.budget === 6000 ? 5000 : 6000} 通勤 ${prefs.commute === 45 ? 30 : 45} 分钟 重新推荐`,
              )
            }
            className="text-xs bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1.5 transition-colors"
          >
            试试{prefs.budget === 6000 ? '预算 5,000' : '预算 6,000'} / 通勤{' '}
            {prefs.commute === 45 ? '30' : '45'} 分钟
          </button>
        </div>
      </div>
    </>
  );
}
