import type { House } from '../types';
import { fmt } from './utils';

export type VerifyResult = '一致' | '冲突' | '未约定' | '无法判断';

export interface VerificationRow {
  claim: string;
  field: string;
  anchor: string | null;
  clauseId: number | null;
  clause: string;
  result: VerifyResult;
  advice: string;
}

export const VR_STYLE: Record<VerifyResult, string> = {
  一致: 'bg-green-50 text-green-600 border-green-100',
  冲突: 'bg-red-50 text-red-500 border-red-100',
  未约定: 'bg-amber-50 text-amber-600 border-amber-100',
  无法判断: 'bg-gray-100 text-gray-500 border-gray-200',
};

/** 核验表：房源承诺 / 合同条款 / 结果 / 建议（与原型内置演示条款一致） */
export function buildVerification(h: House): VerificationRow[] {
  const rows: VerificationRow[] = [];
  // 月租
  if (h.rent != null)
    rows.push({
      claim: `月租 ${fmt(h.rent)} 元`,
      field: '租金',
      anchor: 'hd-rent',
      clauseId: 4,
      clause: '第 4 条：月租 6,000 元',
      result: h.rent === 6000 ? '一致' : '冲突',
      advice: h.rent === 6000 ? '金额一致，按约履行即可' : `与房东确认沟通价 ${fmt(h.rent)} 元，要求修改第 4 条后再签字`,
    });
  // 押金方式
  if (h.deposit)
    rows.push({
      claim: h.deposit,
      field: '押金/付款方式',
      anchor: 'hd-deposit',
      clauseId: 5,
      clause: '第 5 条：押二付一',
      result: h.deposit === '押二付一' ? '一致' : '冲突',
      advice:
        h.deposit === '押二付一'
          ? '与约定一致'
          : `按「${h.deposit}」修改支付方式，测算新增资金占用（押金多付一个月租金）`,
    });
  // 物业费
  if (h.propertyBear || h.propertyFee != null)
    rows.push({
      claim: `物业费${h.propertyBear ? '由' + h.propertyBear : ' ' + fmt(h.propertyFee) + ' 元/月'}`,
      field: '物业费',
      anchor: 'hd-property',
      clauseId: 9,
      clause: '第 9 条：物业费由乙方承担',
      result: h.propertyBear === '租客承担' ? '一致' : '冲突',
      advice:
        h.propertyBear === '租客承担'
          ? '与约定一致'
          : '口头承诺与合同冲突，标记为高优先级确认项，签约前必须修改',
    });
  // 宠物
  if (h.pet)
    rows.push({
      claim: h.pet,
      field: '宠物',
      anchor: 'hd-pet',
      clauseId: 13,
      clause: '第 13 条：禁止饲养任何宠物',
      result: h.pet.includes('禁止') ? '一致' : '冲突',
      advice: h.pet.includes('禁止') ? '与约定一致' : '将宠物约定写入补充协议，注明数量、品种与退租恢复责任',
    });
  // 可入住时间
  if (h.available)
    rows.push({
      claim: h.available,
      field: '可入住时间',
      anchor: 'hd-available',
      clauseId: 3,
      clause: '第 3 条：2026 年 9 月 15 日起租',
      result: '冲突',
      advice: '起租日晚于沟通入住时间会产生空置期租金，建议按实际入住日起租或减免空置期',
    });
  // 面积
  if (h.area != null)
    rows.push({
      claim: `建筑面积 ${h.area} ㎡`,
      field: '面积',
      anchor: null,
      clauseId: 2,
      clause: '第 2 条：建筑面积 68.5 平方米',
      result: h.area === 68.5 ? '一致' : '冲突',
      advice: h.area === 68.5 ? '与合同一致' : '以产权证明为准核实面积差异',
    });
  // 合同未覆盖的房源信息
  if (h.metro)
    rows.push({
      claim: `近地铁（${h.metro}）`,
      field: '位置',
      anchor: null,
      clauseId: null,
      clause: '未找到对应条款',
      result: '未约定',
      advice: '位置信息属房源描述，无需写入合同；如有通勤补贴类承诺需补充约定',
    });
  rows.push({
    claim: '家电维修 24 小时响应（口头承诺）',
    field: '维修',
    anchor: null,
    clauseId: null,
    clause: '未找到对应条款',
    result: '未约定',
    advice: '要求写入补充协议：非人为损坏由甲方负责维修并约定响应时限',
  });
  return rows;
}
