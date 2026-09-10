import type { House, Preferences } from '../types';
import { fmt } from './utils';

/** 硬约束校验：返回违反项（空数组 = 满足全部硬约束） */
export function hardCheck(h: House, prefs: Preferences): string[] {
  const v: string[] = [];
  if (h.rent == null) {
    v.push('月租缺失（关键硬约束无法验证，不可直接推荐）');
  } else if (prefs.budget != null && h.rent > prefs.budget) {
    v.push(`月租 ${fmt(h.rent)} 超出预算 ${fmt(prefs.budget)}`);
  }
  if (h.commuteMin == null) {
    v.push('通勤时间缺失（关键硬约束无法验证，不可直接推荐）');
  } else if (prefs.commute != null && h.commuteMin > prefs.commute) {
    v.push(`通勤 ${h.commuteMin} 分钟超出上限 ${prefs.commute} 分钟`);
  }
  if (prefs.needBathroom && h.bathroom !== true) {
    v.push(h.bathroom === false ? '无独立卫浴（硬约束不满足）' : '独立卫浴情况待确认（硬约束无法验证）');
  }
  return v;
}

/** 软偏好评分：只影响排序，并在结果中说明取舍 */
export function softScore(
  h: House,
  prefs: Preferences,
): { hits: string[]; miss: string[]; score: number } {
  const hits: string[] = [];
  const miss: string[] = [];
  const s = prefs.soft;
  if (s.south) (h.orientation || '').includes('南') ? hits.push('南向') : miss.push('非南向');
  if (s.light) (h.lighting || '').includes('好') ? hits.push('采光好') : miss.push('采光未确认');
  if (s.highFloor) {
    const fl = parseInt(h.floor, 10);
    fl >= 6 ? hits.push('中高楼层') : miss.push('楼层偏低');
  }
  if (s.bigArea) (h.area || 0) >= 50 ? hits.push('面积 ' + h.area + '㎡') : miss.push('面积不大');
  if (s.flexPay) (h.deposit || '').includes('付一') ? hits.push('付款灵活') : miss.push('付款压力大');
  return { hits, miss, score: hits.length };
}
