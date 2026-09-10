import { useState } from 'react';
import type { VerificationResult } from '../../types';
import { getContract, getHouse } from '../../lib/selectors';
import { buildVerification, VR_STYLE, type VerificationRow } from '../../lib/verification';
import { closeContract, copyScript, openContract, openHouseDrawer, send, toast } from '../../controller';

function VerifyRow({
  row,
  index,
  houseId,
  contractId,
  readOnly,
}: {
  row: VerificationRow;
  index: number;
  houseId: string;
  contractId: string;
  readOnly?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-t border-gray-50">
      <button
        type="button"
        className="w-full text-left verify-row p-0 transition-colors focus:outline-none focus:bg-gray-50"
        aria-expanded={open}
        aria-controls={`vr-${index}`}
        onClick={() => setOpen((v) => !v)}
      >
        <div className="grid grid-cols-[1fr_1fr_64px] gap-x-3 px-4 py-2.5 text-[12px] items-start">
          <span className="text-gray-800">{row.claim}</span>
          <span className={row.clauseId ? 'text-gray-500' : 'text-gray-300'}>{row.clause}</span>
          <span
            className={`text-[10px] font-bold px-1.5 py-0.5 rounded border text-center ${VR_STYLE[row.result]}`}
          >
            {row.result}
          </span>
        </div>
      </button>
      <div id={`vr-${index}`} className={open ? 'px-4 pb-3' : 'hidden px-4 pb-3'}>
        <div className="bg-gray-50 rounded-xl px-3 py-2.5 space-y-1.5">
          <div className="text-[11px] text-amber-700">
            <i className="fas fa-lightbulb mr-1"></i>
            <b>建议：</b>
            {row.advice}
          </div>
          <div className="flex gap-2 pt-1">
            {!readOnly && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  closeContract();
                  openHouseDrawer(houseId, row.anchor || undefined);
                }}
                className="text-[11px] bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1 transition-colors"
              >
                <i className="fas fa-building mr-1"></i>定位房源字段
              </button>
            )}
            {row.clauseId ? (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  openContract(row.clauseId, contractId);
                }}
                className="text-[11px] bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1 transition-colors"
              >
                <i className="fas fa-file-lines mr-1"></i>定位合同原文
              </button>
            ) : (
              <span className="text-[10px] text-gray-300 self-center">合同未约定，无法定位</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/** 服务端核验行（clauseId 可点进合同抽屉，anchor 可定位房源字段） */
function ServerVerifyRow({
  item,
  index,
  houseId,
  contractId,
  readOnly,
}: {
  item: VerificationResult['items'][number];
  index: number;
  houseId: string;
  contractId: string;
  readOnly?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const clauseId = item.clause_no ?? null;
  const clause = clauseId
    ? `第 ${clauseId} 条：${(item.clause_text || '').slice(0, 14)}${item.page ? ` · P${item.page}` : ''}`
    : '未找到对应条款';
  return (
    <div className="border-t border-gray-50">
      <button
        type="button"
        className="w-full text-left verify-row p-0 transition-colors focus:outline-none focus:bg-gray-50"
        aria-expanded={open}
        aria-controls={`vr-${index}`}
        onClick={() => setOpen((v) => !v)}
      >
        <div className="grid grid-cols-[1fr_1fr_64px] gap-x-3 px-4 py-2.5 text-[12px] items-start">
          <span className="text-gray-800">
            {item.claim}
            {item.field ? <span className="text-[10px] text-gray-400 ml-1">（{item.field}）</span> : null}
          </span>
          <span className={clauseId ? 'text-gray-500' : 'text-gray-300'}>{clause}</span>
          <span
            className={`text-[10px] font-bold px-1.5 py-0.5 rounded border text-center ${VR_STYLE[item.result]}`}
          >
            {item.result}
          </span>
        </div>
      </button>
      <div id={`vr-${index}`} className={open ? 'px-4 pb-3' : 'hidden px-4 pb-3'}>
        <div className="bg-gray-50 rounded-xl px-3 py-2.5 space-y-1.5">
          {item.clause_text && <div className="text-[11px] text-gray-500">合同原文：{item.clause_text}</div>}
          {item.reason && <div className="text-[11px] text-gray-500">判断依据：{item.reason}</div>}
          <div className="text-[11px] text-amber-700">
            <i className="fas fa-lightbulb mr-1"></i>
            <b>建议：</b>
            {item.advice}
          </div>
          <div className="flex gap-2 pt-1">
            {!readOnly && item.anchor && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  closeContract();
                  openHouseDrawer(houseId, item.anchor || undefined);
                }}
                className="text-[11px] bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1 transition-colors"
              >
                <i className="fas fa-building mr-1"></i>定位房源字段
              </button>
            )}
            {clauseId ? (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  openContract(clauseId, contractId);
                }}
                className="text-[11px] bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1 transition-colors"
              >
                <i className="fas fa-file-lines mr-1"></i>定位合同原文
              </button>
            ) : (
              <span className="text-[10px] text-gray-300 self-center">合同未约定，无法定位</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/** 服务端核验结果（契约 §4.7：结果含一致/冲突/未约定/无法判断 + 原文定位） */
function ServerVerifyCard({ data, houseId, readOnly }: { data: VerificationResult; houseId: string; readOnly?: boolean }) {
  const h = getHouse(houseId);
  const c = getContract(data.contractId);
  if (!h || !c) return null;
  const count = (result: VerificationResult['items'][number]['result']) =>
    Number(data.summary?.[result] ?? data.items.filter((i) => i.result === result).length);
  const conflicts = count('冲突');
  const unbooked = count('未约定');
  const consistent = count('一致');
  const unknown = count('无法判断');
  const high = (data.summary?.high_priority as string[] | undefined) ?? [];

  return (
    <>
      <div className="text-[14px] text-gray-800 mb-2.5 leading-relaxed">
        已将房源 <b>{h.no}</b> 与合同 <b>{c.no}</b> 逐项核验：
        <span className="text-red-600 font-medium">{conflicts} 项冲突</span>
        {unbooked ? (
          <>
            、<span className="text-amber-600 font-medium">{unbooked} 项未约定</span>
          </>
        ) : null}
        {unknown ? (
          <>
            、<span className="text-gray-500 font-medium">{unknown} 项无法判断</span>
          </>
        ) : null}
        {consistent ? `、${consistent} 项一致` : ''}。点击每一项可同时查看房源字段来源与合同原文：
      </div>
      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
        <div className="px-4 py-3 flex items-center justify-between bg-gray-50/80 border-b border-gray-100 flex-wrap gap-1.5">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-gray-900">
            <i className="fas fa-code-compare text-brand-600"></i> 房源承诺 × 合同条款核验
            <span className="text-[10px] bg-green-50 text-green-600 border border-green-100 rounded px-1.5 py-0.5 ml-1">
              服务端核验
            </span>
          </div>
          <div className="text-[10px] text-gray-400">
            {h.no} {h.name} × {c.no} {c.name}
            {data.items[0]?.page ? ` · 首个条款 P${data.items[0].page}` : ''}
          </div>
        </div>
        <div className="grid grid-cols-[1fr_1fr_64px] gap-x-3 px-4 py-2 text-[10px] font-semibold text-gray-400 border-b border-gray-100">
          <span>房源信息 / 承诺</span>
          <span>合同对应条款</span>
          <span>结果</span>
        </div>
        {data.items.map((item, i) => (
          <ServerVerifyRow
            key={item.id}
            item={item}
            index={i}
            houseId={h.id}
            contractId={c.id}
            readOnly={readOnly}
          />
        ))}
        <div className="px-4 py-3 border-t border-gray-100 bg-red-50/40">
          <div className="text-[11px] font-semibold text-red-500 mb-1">
            <i className="fas fa-comments mr-1"></i>修改建议与谈判话术
          </div>
          <div className="text-[11px] text-gray-600 leading-relaxed">
            以上是风险提示与谈判建议，不构成法律结论。建议将 {conflicts} 处冲突逐条与房东书面确认后再签约。
            {high.length ? `高优先级：${high.join('、')}。` : ''}
          </div>
          {data.negotiation && (
            <pre className="mt-2 text-[11px] text-gray-600 bg-white border border-gray-100 rounded-xl px-3 py-2 whitespace-pre-wrap font-sans">
              {data.negotiation}
            </pre>
          )}
          <div className="flex flex-wrap gap-2 mt-2.5">
            <button
              onClick={() => {
                navigator.clipboard?.writeText(data.negotiation || '');
                toast('谈判话术已复制到剪贴板');
              }}
              className="text-[11px] bg-gray-900 hover:bg-gray-700 text-white rounded-full px-3 py-1.5 transition-colors"
            >
              <i className="fas fa-copy mr-1"></i>复制谈判话术
            </button>
            <button
              onClick={() => send('物业费谁承担？')}
              className="text-[11px] bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1.5 transition-colors"
            >
              追问：物业费谁承担？
            </button>
            <button
              onClick={() => send('提前退租要付什么？')}
              className="text-[11px] bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1.5 transition-colors"
            >
              追问：提前退租要付什么？
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

export function VerifyCard({
  houseId,
  contractId,
  readOnly,
  data,
}: {
  houseId: string;
  contractId: string;
  readOnly?: boolean;
  data?: VerificationResult;
}) {
  if (data) return <ServerVerifyCard data={data} houseId={houseId} readOnly={readOnly} />;
  const h = getHouse(houseId);
  const c = getContract(contractId);
  if (!h || !c) return null;
  const rows = buildVerification(h);
  const conflicts = rows.filter((r) => r.result === '冲突').length;
  const unbooked = rows.filter((r) => r.result === '未约定').length;

  return (
    <>
      <div className="mb-2 text-[12px] text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-3.5 py-2.5 flex items-center gap-2">
        <i className="fas fa-flask text-amber-600 shrink-0"></i>
        <span>
          <b>合同演示解析提示：</b>当前前端原型使用内置演示条款与金额进行核验演示，尚未对接后端真实合同解析服务。
        </span>
      </div>
      <div className="text-[14px] text-gray-800 mb-2.5 leading-relaxed">
        已将房源 <b>{h.no}</b> 与合同 <b>{c.no}</b> 逐项核验：
        <span className="text-red-600 font-medium">{conflicts} 项冲突</span>
        {unbooked ? (
          <>
            、<span className="text-amber-600 font-medium">{unbooked} 项未约定</span>
          </>
        ) : null}
        。点击每一项可同时查看房源字段来源与合同原文：
      </div>
      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
        <div className="px-4 py-3 flex items-center justify-between bg-gray-50/80 border-b border-gray-100 flex-wrap gap-1.5">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-gray-900">
            <i className="fas fa-code-compare text-brand-600"></i> 房源承诺 × 合同条款核验{' '}
            <span className="text-[10px] bg-amber-100 text-amber-700 border border-amber-200 rounded px-1.5 py-0.5 ml-1">
              演示解析
            </span>
          </div>
          <div className="text-[10px] text-gray-400">
            {h.no} {h.name} × {c.no} {c.name}
          </div>
        </div>
        <div className="grid grid-cols-[1fr_1fr_64px] gap-x-3 px-4 py-2 text-[10px] font-semibold text-gray-400 border-b border-gray-100">
          <span>房源信息 / 承诺</span>
          <span>合同对应条款</span>
          <span>结果</span>
        </div>
        {rows.map((r, i) => (
          <VerifyRow
            key={i}
            row={r}
            index={i}
            houseId={h.id}
            contractId={c.id}
            readOnly={readOnly}
          />
        ))}
        <div className="px-4 py-3 border-t border-gray-100 bg-red-50/40">
          <div className="text-[11px] font-semibold text-red-500 mb-1">
            <i className="fas fa-comments mr-1"></i>修改建议与谈判话术
          </div>
          <div className="text-[11px] text-gray-600 leading-relaxed">
            以上是风险提示与谈判建议，不构成法律结论。建议将 {conflicts} 处冲突逐条与房东书面确认后再签约。
          </div>
          <div className="flex flex-wrap gap-2 mt-2.5">
            <button
              onClick={() => copyScript(c.id)}
              className="text-[11px] bg-gray-900 hover:bg-gray-700 text-white rounded-full px-3 py-1.5 transition-colors"
            >
              <i className="fas fa-copy mr-1"></i>复制谈判话术
            </button>
            <button
              onClick={() => send('物业费谁承担？')}
              className="text-[11px] bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1.5 transition-colors"
            >
              追问：物业费谁承担？
            </button>
            <button
              onClick={() => send('提前退租要付什么？')}
              className="text-[11px] bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1.5 transition-colors"
            >
              追问：提前退租要付什么？
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
