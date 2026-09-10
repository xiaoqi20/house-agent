import type { Contract, DemoStore, House, Preferences, SourceKey } from '../types';
import { nid } from '../lib/utils';

export function cloneHouse(h: House): House {
  return { ...h, visits: h.visits.map((v) => ({ ...v })), todos: [...h.todos], verify: [...h.verify] };
}

export function clonePrefs(p: Preferences): Preferences {
  return { ...p, soft: { ...p.soft } };
}

export const SOURCE_LABEL: Record<string, string> = {
  paste: '用户粘贴',
  manual: '手动填写',
  batch: '批量粘贴',
  'file-xlsx': 'Excel 导入',
  'file-docx': 'Word 导入',
  'file-txt': '文本文件导入',
  link: '外部链接',
};

let houseSeq = 0;
let contractSeq = 0;
let batchSeq = 0;

export function nextBatchId(): string {
  return 'B-' + String(++batchSeq).padStart(3, '0');
}

export function mkHouse(d: Partial<House> = {}): House {
  return Object.assign(
    {
      id: nid(),
      no: 'H' + ++houseSeq,
      batch: null,
      status: 'active' as const,
      dropReason: '',
      source: 'paste' as SourceKey,
      raw: '',
      name: '',
      region: '',
      address: '',
      rent: null,
      deposit: '',
      agencyFee: null,
      propertyFee: null,
      propertyBear: '',
      netFee: null,
      otherFee: '',
      area: null,
      layout: '',
      floor: '',
      orientation: '',
      bathroom: null,
      lighting: '',
      furniture: '',
      commuteMin: null,
      commuteMode: '地铁',
      metro: '',
      nearby: '',
      pet: '',
      shared: false,
      sublet: '',
      maxPeople: null,
      leaseReq: '',
      available: '',
      notes: '',
      visits: [],
      todos: [],
      verify: [],
      contractId: null,
      linkUrl: '',
    },
    d,
  );
}

export function mkContract(d: Partial<Contract> = {}): Contract {
  return Object.assign(
    {
      id: nid(),
      no: 'C' + ++contractSeq,
      name: '',
      source: '上传',
      time: new Date().toISOString().slice(0, 10),
      status: 'done' as const,
      reason: '',
      size: '',
      boundHouseId: null,
      clausesList: [],
      riskClauses: [],
      negotiation: '',
    },
    d,
  );
}

/** 将一段文本解析为候选房源（原型内置的轻量规则解析，不调用后端） */
export function parseHousesInput(text: string): House[] {
  let parts = text
    .split(/[\n;；]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (parts.length <= 2 && /[①②③④⑤⑥⑦⑧⑨⑩]|(?<!\d)\d+[.、](?!\d)/.test(text)) {
    parts = text
      .split(
        /(?=[①②③④⑤⑥⑦⑧⑨⑩]|(?<!\d)\d+[.、](?!\d)|(?<!\d)[(（\[【]\d+[)）\]】]|(?:^|\s)房源[A-Za-z0-9一二三四五六]?[：:])/,
      )
      .map((s) => s.trim())
      .filter(Boolean);
  }
  function isHouseLine(p: string): boolean {
    if (
      /^(?:我输入|帮我|请帮|房源对比|有三套|这几套|三套房源|房源如下|对比)/.test(p) &&
      !/(?:平|㎡|开间|次卧|主卧|一居|两居|\/月)/.test(p)
    )
      return false;
    const hasPrice = /(?:\d{3,5}\s*(?:\/月|元\/月|元)|押[一二三两]付)/i.test(p);
    const hasTypeOrArea =
      /(?:\d+(?:\.\d+)?\s*(?:平|㎡|平米)|一居|两居|三居|四居|开间|次卧|主卧|合租|整租)/.test(p);
    const hasCommuteOrFloor = /(?:地铁|\d+\s*分钟|\d+楼|\d+层|[东西南北]向)/.test(p);
    return (hasPrice && hasTypeOrArea) || (hasPrice && hasCommuteOrFloor) || (hasTypeOrArea && hasCommuteOrFloor);
  }
  const out: House[] = [];
  parts
    .filter(isHouseLine)
    .forEach((part, idx) => {
      const clean = part
        .replace(
          /^(?:[①②③④⑤⑥⑦⑧⑨⑩]|(?:\d+|[一二三四五六七八九十])[.、\s]+|[(（\[【]?\d+[)）\]】]|房源[A-Za-z0-9一二三四五六]?[：:]\s*)+/,
          '',
        )
        .trim();
      if (!clean) return;
      const h = mkHouse({ source: 'batch', raw: clean });
      const rMatch = clean.match(/(\d{3,5})\s*(?:\/月|元\/月|元)/);
      if (rMatch) h.rent = parseInt(rMatch[1], 10);
      const depMatch = clean.match(/(押[一二三两]付[一二三两月六]+|无押金)/);
      if (depMatch) h.deposit = depMatch[1];
      const aMatch = clean.match(/(\d+(?:\.\d+)?)\s*(?:平米|平|㎡)/);
      if (aMatch) h.area = parseFloat(aMatch[1]);
      const commMatch = clean.match(/(?:地铁\s*|通勤\s*约?)?(\d{1,3})\s*分钟/);
      if (commMatch) h.commuteMin = parseInt(commMatch[1], 10);
      const flMatch = clean.match(/(\d+(?:\/\d+)?(?:楼|层))/);
      if (flMatch) h.floor = flMatch[1];
      const orMatch = clean.match(/([东西南北]+向)/);
      if (orMatch) h.orientation = orMatch[1];
      const layMatch = clean.match(
        /((?:一|两|三|四)居(?:合租|整租)?(?:次卧|主卧)?|开间|(?:合租|整租)(?:次卧|主卧)|(?:次卧|主卧))/,
      );
      if (layMatch) h.layout = layMatch[1];
      if (/独立卫浴|独卫/.test(clean)) h.bathroom = true;
      if (/无独卫|公用卫浴|共用卫浴/.test(clean)) h.bathroom = false;
      if (/合租|次卧|主卧/.test(clean)) h.shared = true;
      if (/整租/.test(clean)) h.shared = false;
      if (/允许养|可养|宠物友好/.test(clean)) h.pet = '允许宠物';
      if (/禁止养|不可养|不许养/.test(clean)) h.pet = '禁止宠物';
      const propMatch = clean.match(/物业费\s*(\d{2,4})/);
      if (propMatch) h.propertyFee = parseInt(propMatch[1], 10);
      if (/物业费.{0,6}(房东|甲方)承担|房东承担物业/.test(clean)) h.propertyBear = '房东承担';
      if (/物业费.{0,6}(租客|乙方|自己)承担|自付物业/.test(clean)) h.propertyBear = '租客承担';
      const avMatch = clean.match(/(\d{1,2}月\d{1,2}日|随时|尽快)(?:可)?入住/);
      if (avMatch) h.available = avMatch[0].replace('入住', '') + '可入住';
      const metroMatch = clean.match(/(\d+号线\S{0,10}站)/);
      if (metroMatch) h.metro = metroMatch[1];
      if (/采光好|采光佳/.test(clean)) h.lighting = '采光好';
      let name = clean
        .replace(/(\d{3,5}\s*(?:\/月|元).*$)/, '')
        .replace(/(?:押[一二三两]付.*$)/, '')
        .replace(/[，,;；]/g, ' ')
        .trim();
      if (!name || name.length < 2) {
        const nm = clean.match(/^([^\d,，\s/]+)/);
        name = nm ? nm[1] : `房源 ${idx + 1}`;
      }
      if (name.length > 18) name = name.slice(0, 18);
      h.name = name;
      out.push(h);
    });
  return out;
}

export const DEMO_BATCH_TEXT = `① 望京南湖东园一居 整租 5800/月 押一付一 68.5平 12/18层 南向 独立卫浴 采光好 地铁14号线望京站350米 通勤35分钟 物业费房东承担 允许养猫 10月1日可入住 家具家电齐全
② 酒仙桥将府家园开间 整租 4600/月 押一付一 42平 3/6层 东向 独立卫浴 地铁14号线将台站 通勤42分钟 网费50/月 随时可入住 禁止养宠物
③ 将台两居合租次卧 3800/月 押一付三 18平 8/11层 北向 无独卫 地铁30分钟 中介费半个月租金 限住1人
④ 大望路现代城一居 整租 6200/月 独立卫浴 通勤22分钟 南向 来自链家链接 押金和物业费待与中介确认
⑤ 芍药居主卧带独卫 合租 4100/月 押一付一 独立卫浴 通勤40分钟 北向 可养猫 房东直租无中介费`;

export function enrichDemo(list: House[]): House[] {
  const batchId = nextBatchId();
  list.forEach((h) => {
    h.batch = batchId;
  });
  const L = list;
  if (L[0])
    Object.assign(L[0], {
      region: '朝阳·望京',
      propertyFee: 120,
      propertyBear: '房东承担',
      netFee: 0,
      lighting: '采光好',
      furniture: '家具家电齐全',
      verify: ['月租与押金方式需与房东书面确认', '物业费承担方需写入合同', '宠物约定需写入补充协议'],
      todos: ['确认 10 月 1 日能否准时交房', '询问家电维修责任'],
    });
  if (L[1])
    Object.assign(L[1], {
      region: '朝阳·酒仙桥',
      propertyFee: 80,
      propertyBear: '租客承担',
      netFee: 50,
      available: '随时可入住',
      pet: '禁止宠物',
      verify: ['低楼层潮湿情况需实地确认'],
      todos: ['确认商水商电还是民水民电'],
    });
  if (L[2])
    Object.assign(L[2], {
      region: '朝阳·将台',
      agencyFee: 1900,
      maxPeople: 1,
      verify: ['合租公区费用分摊规则待确认', '室友情况未知'],
      todos: ['确认能否短租', '确认公区保洁频率'],
    });
  if (L[3])
    Object.assign(L[3], {
      source: 'link' as SourceKey,
      linkUrl: 'https://bj.lianjia.com/zufang/demo（仅记录来源，不代表实时同步，房源是否仍在需自行核实）',
      region: '朝阳·大望路',
      verify: ['押金方式待与中介确认', '物业费金额与承担方待确认', '链接仅作来源记录，房源是否仍在需自行核实'],
      todos: ['向中介索要费用明细'],
    });
  if (L[4])
    Object.assign(L[4], {
      region: '朝阳·芍药居',
      agencyFee: 0,
      pet: '可养猫',
      verify: ['主卧独卫为房东口头承诺，需看房确认'],
      todos: ['确认合租人数上限'],
    });
  return list;
}

export function demoHouses(source?: SourceKey): House[] {
  const list = parseHousesInput(DEMO_BATCH_TEXT);
  list.forEach((h) => {
    h.source = source || h.source;
  });
  return enrichDemo(list);
}

// ==================== 合同演示数据 ====================

export const DEMO_CONTRACT_TEXT = `北京市房屋租赁合同\n出租方（甲方）：王某  承租方（乙方）：张三\n第二条 租赁房屋：甲方将位于北京市朝阳区望京南湖东园一区 3 号楼 1202 室出租给乙方，建筑面积 68.5 平方米。\n第三条 租赁期限：共 12 个月，自 2026 年 9 月 15 日起至 2027 年 9 月 14 日止。\n第四条 租金：月租金为人民币 6,000 元。\n第五条 押金与支付：乙方按押二付一方式支付，签约当日支付押金 12,000 元。\n第八条 违约责任：任何一方违约，应向守约方支付违约金，金额为月租金的三倍。\n第九条 物业费：租赁期内物业费由乙方承担。\n第十三条 其他约定：租赁期内乙方不得在房屋内饲养任何宠物。`;

export const DEMO_CONTRACT_CLAUSES: Array<[number, string, string]> = [
  [2, '第二条 租赁房屋', '甲方将位于北京市朝阳区望京南湖东园一区 3 号楼 1202 室出租给乙方居住使用，建筑面积 68.5 平方米。'],
  [3, '第三条 租赁期限', '租赁期共 12 个月，自 2026 年 9 月 15 日起至 2027 年 9 月 14 日止。'],
  [4, '第四条 租金', '月租金为人民币 6,000 元，乙方应于每期开始前 7 日支付。'],
  [5, '第五条 押金与支付', '乙方按「押二付一」方式支付，签约当日支付押金人民币 12,000 元。'],
  [8, '第八条 违约责任', '任何一方违约的，应向守约方支付违约金，违约金金额为月租金的三倍，并赔偿由此造成的全部损失。'],
  [9, '第九条 物业费', '租赁期内，该房屋物业费由乙方承担，随租金一并缴纳。'],
  [13, '第十三条 其他约定', '租赁期内，乙方不得在房屋内饲养任何宠物；违反的，甲方有权解除合同并没收押金。'],
];

export function buildBoundContract(
  name: string,
  source: string,
  size: string,
  houseId: string | null,
): Contract {
  return mkContract({
    name: name.includes('演示解析') ? name : `${name}（演示解析）`,
    source,
    size,
    boundHouseId: houseId,
    isDemoParse: true,
    clausesList: DEMO_CONTRACT_CLAUSES,
    riskClauses: [4, 5, 8, 9, 13],
    negotiation: `建议与房东确认并修改的条款（可发给房东）：\n1. 第 4 条：月租由 6,000 元改回沟通价 5,800 元；\n2. 第 5 条：支付方式由「押二付一」改为「押一付一」，减少资金占用 6,000 元；\n3. 第 9 条：物业费按口头约定由甲方承担，或从月租中扣除；\n4. 第 13 条：删除禁养条款，改为「乙方饲养一只已免疫宠物猫，退租时恢复原状」；\n5. 第 8 条：违约金由三个月租金改为一个月租金。`,
  });
}

// ==================== 历史演示会话数据（只读快照） ====================

let demoStore: DemoStore | null = null;

export function getDemoStore(): DemoStore {
  if (!demoStore) {
    const dHouses = demoHouses('batch');
    if (dHouses[4]) dHouses[4].source = 'manual';
    const h0 = dHouses[0];
    const dContract = buildBoundContract('北京市房屋租赁合同（望京）.pdf', '上传', '2.4 MB', h0.id);
    h0.contractId = dContract.id;
    demoStore = { houses: dHouses, contracts: [dContract], targetHouse: h0, targetContract: dContract };
  }
  return demoStore;
}
