/** 后端 DTO → 前端领域类型（web/src/types.ts、lib/verification.ts）。 */

import type { Contract, House, Message, Preferences, RecommendationResult, VerificationResult } from '../types';
import type { VerificationRow } from '../lib/verification';
import { answerHTML } from '../lib/answers';
import { textBubble } from '../lib/seeds';
import type {
  AnswerDto,
  ContractDto,
  HouseDto,
  HouseDraftDto,
  MessageDto,
  PreferenceDto,
  RecommendationDto,
  VerificationDto,
  VerificationItemDto,
} from './types';

export function houseFromDto(dto: HouseDto): House {
  return {
    id: dto.id,
    no: dto.no,
    batch: dto.batch_id ? `B-${dto.batch_id.slice(0, 4).toUpperCase()}` : null, // 批次 uuid 只显示短标签，原型是 B-001
    status: dto.status,
    dropReason: dto.drop_reason,
    source: dto.source,
    raw: dto.raw,
    name: dto.name,
    region: dto.region,
    address: dto.address,
    rent: dto.rent,
    deposit: dto.deposit,
    agencyFee: dto.agency_fee,
    propertyFee: dto.property_fee,
    propertyBear: dto.property_bear,
    netFee: dto.net_fee,
    otherFee: dto.other_fee,
    area: dto.area,
    layout: dto.layout,
    floor: dto.floor,
    orientation: dto.orientation,
    bathroom: dto.bathroom,
    lighting: dto.lighting,
    furniture: dto.furniture,
    commuteMin: dto.commute_min,
    commuteMode: dto.commute_mode,
    metro: dto.metro,
    nearby: dto.nearby,
    pet: dto.pet,
    shared: dto.shared,
    sublet: dto.sublet,
    maxPeople: dto.max_people,
    leaseReq: dto.lease_req,
    available: dto.available,
    notes: dto.notes,
    visits: dto.visits ?? [],
    todos: dto.todos ?? [],
    verify: dto.verify ?? [],
    contractId: dto.contract_id,
    linkUrl: dto.link_url,
  };
}

/** 前端 House → 确认接口的请求体（字段确认面板改过的值 + 原文依据） */
export function houseToConfirm(house: House, sourceLabel: string, evidence: Record<string, string> = {}) {
  return {
    draft_id: null,
    name: house.name,
    region: house.region,
    address: house.address,
    rent: house.rent,
    deposit: house.deposit,
    agency_fee: house.agencyFee,
    property_fee: house.propertyFee,
    property_bear: house.propertyBear,
    net_fee: house.netFee,
    other_fee: house.otherFee,
    area: house.area,
    layout: house.layout,
    floor: house.floor,
    orientation: house.orientation,
    bathroom: house.bathroom,
    lighting: house.lighting,
    furniture: house.furniture,
    commute_min: house.commuteMin,
    commute_mode: house.commuteMode,
    metro: house.metro,
    nearby: house.nearby,
    pet: house.pet,
    shared: house.shared,
    sublet: house.sublet,
    max_people: house.maxPeople,
    lease_req: house.leaseReq,
    available: house.available,
    notes: house.notes,
    link_url: house.linkUrl,
    source: house.source,
    raw: house.raw || sourceLabel,
    evidence,
    verify: house.verify,
    todos: house.todos,
  };
}

export function contractFromDto(dto: ContractDto): Contract {
  return {
    id: dto.id,
    no: dto.no,
    name: dto.name,
    source: dto.source === 'paste' ? '粘贴文本' : dto.source.toUpperCase(),
    time: dto.time,
    status: dto.status === 'failed' ? 'failed' : 'done',
    reason: dto.reason,
    size: dto.size,
    boundHouseId: dto.bound_house_id,
    clausesList: dto.clauses_list.map(([no, title, text]) => [no ?? 0, title, text] as [number, string, string]),
    riskClauses: dto.risk_clauses,
    negotiation: dto.negotiation,
  };
}

export function prefsFromDto(dto: PreferenceDto): Preferences {
  return {
    budget: dto.budget,
    commute: dto.commute,
    needBathroom: dto.need_bathroom,
    allowShared: dto.allow_shared,
    soft: {
      south: dto.soft.south,
      light: dto.soft.light,
      highFloor: dto.soft.high_floor,
      bigArea: dto.soft.big_area,
      flexPay: dto.soft.flex_pay,
    },
  };
}

export function prefsToDto(prefs: Preferences): Omit<PreferenceDto, 'version'> {
  return {
    budget: prefs.budget,
    commute: prefs.commute,
    need_bathroom: prefs.needBathroom,
    allow_shared: prefs.allowShared,
    soft: {
      south: prefs.soft.south,
      light: prefs.soft.light,
      high_floor: prefs.soft.highFloor,
      big_area: prefs.soft.bigArea,
      flex_pay: prefs.soft.flexPay,
    },
  };
}

/** 核验项 → 核验表行（clauseId 用条号，抽屉按条号定位） */
export function verificationRows(items: VerificationItemDto[]): VerificationRow[] {
  return items.map((item) => ({
    claim: item.claim,
    field: item.field,
    anchor: item.anchor,
    clauseId: item.clause_no,
    clause: item.clause_no ? `第 ${item.clause_no} 条：${(item.clause_text || '').slice(0, 14)}` : '未找到对应条款',
    result: item.result,
    advice: item.advice,
  }));
}

/** 推荐响应 → 渲染用结果（三视图 + explanation，全部来自服务端） */
export function recommendationResult(dto: RecommendationDto): RecommendationResult {
  const snapshot = (dto.snapshot ?? {}) as { houses?: HouseDto[]; prefs?: PreferenceDto };
  const about = dto.about ?? {};
  return {
    id: dto.id,
    view: dto.view,
    prefsVersion: dto.prefs_version,
    houses: (snapshot.houses ?? []).map(houseFromDto),
    views: dto.views,
    explanation: dto.explanation ?? {},
    about: {
      hardRules: about.hard_rules ?? [],
      softRules: about.soft_rules ?? [],
      window: about.window ?? null,
      missing: about.missing ?? [],
    },
  };
}

/** 核验响应 → 渲染用结果 */
export function verificationResult(dto: VerificationDto): VerificationResult {
  return {
    id: dto.id,
    houseId: dto.house_id,
    contractId: dto.contract_id,
    items: dto.items ?? [],
    summary: dto.summary ?? {},
    negotiation: dto.negotiation ?? '',
  };
}

/** 历史消息 → 前端消息（重新打开会话时从服务端读取） */
export function messageFromDto(dto: MessageDto): Message {
  const citations = dto.citations ?? [];
  if (dto.role === 'user') {
    return { id: dto.id, role: 'user', content: { type: 'html', html: textBubble(dto.content?.text ?? '') } };
  }
  return {
    id: dto.id,
    role: 'ai',
    actions: true,
    content: {
      type: 'html',
      html: answerHTML({
        message_id: dto.id,
        mode: (dto.content?.mode as AnswerDto['mode']) ?? 'general',
        html: dto.content?.html ?? '',
        citations,
        followups: dto.content?.followups ?? [],
        sources: dto.content?.sources ?? [],
      }),
    },
  };
}

/** 提取草稿 → 字段确认面板行（值以字符串呈现，与原型输入框一致） */
export function draftToPending(draft: HouseDraftDto): House {
  return houseFromDto({
    ...(draft as unknown as HouseDto),
    id: draft.draft_id,
    no: '',
    batch_id: null,
    status: 'active',
    drop_reason: '',
    visits: [],
    todos: [],
    verify: [],
    contract_id: null,
    source_label: '',
    completeness: 0,
    missing: draft.missing ?? [],
  });
}
