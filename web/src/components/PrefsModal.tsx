import { useEffect, useState } from 'react';
import { useStore } from '../store';
import type { Preferences, SoftKey } from '../types';
import { applyPrefs, closePrefs, toggleSoft } from '../controller';

const SOFT_TAGS: Array<[SoftKey, string]> = [
  ['south', '南向优先'],
  ['light', '采光好'],
  ['highFloor', '中高楼层'],
  ['bigArea', '面积更大'],
  ['flexPay', '付款灵活（押一付一）'],
];

export function PrefsModal() {
  const open = useStore((s) => s.prefsOpen);
  const prefs = useStore((s) => s.prefs);
  const [budget, setBudget] = useState('');
  const [commute, setCommute] = useState('');
  const [needBathroom, setNeedBathroom] = useState(false);
  const [allowShared, setAllowShared] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setBudget(prefs.budget == null ? '' : String(prefs.budget));
    setCommute(prefs.commute == null ? '' : String(prefs.commute));
    setNeedBathroom(!!prefs.needBathroom);
    setAllowShared(!!prefs.allowShared);
    setError('');
    // 打开时按当前偏好初始化表单（与原型 openPrefs 一致）
  }, [open]);

  if (!open) return null;

  const save = () => {
    const b = budget.trim();
    const c = commute.trim();
    if (b && (!/^\d+$/.test(b) || +b <= 0)) {
      setError('预算需为正整数（元），例如 6000');
      return;
    }
    if (c && (!/^\d+$/.test(c) || +c <= 0 || +c > 300)) {
      setError('通勤上限需为 1—300 的整数（分钟）');
      return;
    }
    const next: Preferences = {
      budget: b ? +b : null,
      commute: c ? +c : null,
      needBathroom,
      allowShared,
      soft: { ...prefs.soft },
    };
    applyPrefs(next);
  };

  return (
    <div
      id="prefsModal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 fade-in p-4"
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[88vh] flex flex-col">
        <div className="flex items-center justify-between px-6 pt-5 pb-3 shrink-0">
          <div>
            <h3 className="text-[15px] font-semibold text-gray-900">筛选偏好</h3>
            <p className="text-[11px] text-gray-400 mt-0.5">硬约束会淘汰房源，软偏好只影响排序并说明取舍</p>
          </div>
          <button
            onClick={closePrefs}
            aria-label="关闭偏好设置"
            className="w-8 h-8 rounded-lg hover:bg-gray-100 text-gray-400 flex items-center justify-center"
          >
            <i className="fas fa-times"></i>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar px-6 py-4">
          <div className="text-[12px] font-semibold text-red-500 mb-2 flex items-center gap-1.5">
            <i className="fas fa-ban text-[10px]"></i>硬约束（不满足即淘汰 / 标记不满足）
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="text-[12px] text-gray-600">
              月租预算上限（元）
              <input
                id="pf-budget"
                type="number"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                className="mt-1 w-full bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5 text-[13px] outline-none focus:border-gray-300 focus:bg-white"
              />
            </label>
            <label className="text-[12px] text-gray-600">
              通勤上限（分钟）
              <input
                id="pf-commute"
                type="number"
                value={commute}
                onChange={(e) => setCommute(e.target.value)}
                className="mt-1 w-full bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5 text-[13px] outline-none focus:border-gray-300 focus:bg-white"
              />
            </label>
          </div>
          <div className="flex flex-wrap gap-4 mt-3 text-[12px] text-gray-600">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                id="pf-bathroom"
                checked={needBathroom}
                onChange={(e) => setNeedBathroom(e.target.checked)}
                className="w-3.5 h-3.5 rounded border-gray-300 text-brand-500"
              />{' '}
              必须独立卫浴
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                id="pf-shared"
                checked={allowShared}
                onChange={(e) => setAllowShared(e.target.checked)}
                className="w-3.5 h-3.5 rounded border-gray-300 text-brand-500"
              />{' '}
              接受合租（默认不接受）
            </label>
          </div>
          <div className="text-[12px] font-semibold text-brand-600 mt-6 mb-2 flex items-center gap-1.5">
            <i className="fas fa-arrow-up-wide-short text-[10px]"></i>软偏好（只影响排序，会在结果中说明取舍）
          </div>
          <div className="flex flex-wrap gap-2" id="softTags">
            {SOFT_TAGS.map(([key, label]) => (
              <button
                key={key}
                data-soft={key}
                onClick={() => toggleSoft(key)}
                className={`soft-tag ${prefs.soft[key] ? 'on' : ''} text-xs border rounded-full px-3 py-1.5 transition-colors`}
              >
                {label}
              </button>
            ))}
          </div>
          {error && <div className="mt-4 text-[12px] text-red-500">{error}</div>}
        </div>
        <div className="px-6 py-4 border-t border-gray-100 flex gap-2.5 shrink-0">
          <button
            onClick={closePrefs}
            className="flex-1 border border-gray-200 hover:bg-gray-50 text-gray-700 rounded-xl py-2.5 text-[13px] font-medium transition-colors"
          >
            取消
          </button>
          <button
            onClick={save}
            className="flex-1 bg-gray-900 hover:bg-gray-700 text-white rounded-xl py-2.5 text-[13px] font-medium transition-colors"
          >
            保存并重新推荐
          </button>
        </div>
      </div>
    </div>
  );
}
