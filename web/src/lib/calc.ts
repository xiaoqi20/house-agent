import type { House, Preferences } from '../types';

/** 关键字段清单（用于完整度 / 缺失计算） */
export const KEY_FIELDS: Array<[keyof House, string]> = [
  ['rent', '租金'],
  ['deposit', '押金/付款方式'],
  ['propertyFee', '物业费'],
  ['commuteMin', '通勤'],
  ['layout', '户型'],
  ['area', '面积'],
  ['floor', '楼层'],
  ['orientation', '朝向'],
  ['bathroom', '独立卫浴'],
  ['available', '可入住时间'],
  ['pet', '宠物'],
  ['region', '区域'],
];

export function isFilled(h: House, k: keyof House): boolean {
  const v = h[k];
  if (k === 'bathroom') return v === true || v === false;
  return v !== null && v !== '' && v !== undefined;
}

export function missingFields(h: House): string[] {
  return KEY_FIELDS.filter(([k]) => !isFilled(h, k)).map(([, l]) => l);
}

export function completeness(h: House): number {
  const filled = KEY_FIELDS.filter(([k]) => isFilled(h, k)).length;
  return Math.round((filled / KEY_FIELDS.length) * 100);
}

export function monthlyCost(h: House): {
  sum: number;
  unknown: string[];
  isRentMissing: boolean;
} {
  let sum = h.rent != null ? h.rent : 0;
  const unknown: string[] = [];
  if (h.rent == null) unknown.push('租金');
  if (h.propertyFee != null) sum += h.propertyFee;
  else unknown.push('物业费');
  if (h.netFee != null) sum += h.netFee;
  else unknown.push('网费');
  return { sum, unknown, isRentMissing: h.rent == null };
}

export function oneTimeCost(h: House): {
  deposit: number;
  agency: number | null;
  label: string;
} {
  let months = 0;
  const m = (h.deposit || '').match(/押([一二三])付/);
  if (m) months = { 一: 1, 二: 2, 三: 3 }[m[1]] || 0;
  return { deposit: (h.rent || 0) * months, agency: h.agencyFee, label: h.deposit || '待确认' };
}

/** 参与推荐比较所必需的关键字段（租金 / 通勤 / 独立卫浴） */
export function comparisonMissingFields(h: House, prefs: Preferences): string[] {
  const missing: string[] = [];
  if (h.rent == null) missing.push('租金');
  if (h.commuteMin == null) missing.push('通勤');
  if (prefs.needBathroom && h.bathroom !== true && h.bathroom !== false) missing.push('独立卫浴');
  return missing;
}
