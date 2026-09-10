/** 高层 API：控制器只调用这里的方法，演示模式（VITE_API_MODE=demo）保持本地逻辑。 */

import { api, createWorkspace, health } from './client';
import { waitRun, cancelRun, type SubscribeOptions } from './sse';
import {
  contractFromDto,
  houseFromDto,
  houseToConfirm,
  prefsFromDto,
  prefsToDto,
} from './adapter';
import type {
  AnswerDto,
  BatchDto,
  ContractDto,
  ClauseDto,
  ConversationDto,
  HouseDto,
  MessageDto,
  PreferenceDto,
  RecommendationDto,
  RunEventDto,
  VerificationDto,
} from './types';
import type { House, Preferences } from '../types';

export { ApiError } from './client';
export { cancelRun, waitRun } from './sse';
export { API_MODE } from './config';
export * from './adapter';
export type * from './types';

let workspaceId: string | null = null;

/** 本次工作台（一期临时数据边界）：首次调用创建并缓存，刷新后通过 sessionStorage 复用。 */
export async function ensureWorkspace(): Promise<string> {
  if (workspaceId) return workspaceId;
  const cached = sessionStorage.getItem('rg-workspace');
  if (cached) {
    workspaceId = cached;
    return cached;
  }
  const workspace = await createWorkspace();
  workspaceId = workspace.id;
  sessionStorage.setItem('rg-workspace', workspace.id);
  return workspace.id;
}

export function currentWorkspaceId(): string | null {
  return workspaceId;
}

export function resetWorkspace(): void {
  workspaceId = null;
  sessionStorage.removeItem('rg-workspace');
}

export async function ping(): Promise<{ ok: boolean; llm_provider: string }> {
  return health();
}

// ---------------- 导入 ----------------

export async function importText(ws: string, source: string, text: string, linkUrl?: string): Promise<BatchDto> {
  return api.post<BatchDto>('/import-batches', { workspace_id: ws, source, text, link_url: linkUrl });
}

export async function importFile(ws: string, file: File): Promise<BatchDto> {
  const form = new FormData();
  form.append('workspace_id', ws);
  form.append('file', file);
  return api.post<BatchDto>('/import-batches/upload', form);
}

export function getBatch(batchId: string): Promise<BatchDto> {
  return api.get<BatchDto>(`/import-batches/${batchId}`);
}

export async function confirmBatch(
  batchId: string,
  houses: House[],
  evidence: Record<string, Record<string, string>> = {},
): Promise<{ houses: House[]; hint: string }> {
  const payload = {
    houses: houses.map((house) => houseToConfirm(house, house.raw || '用户输入', evidence[house.id] ?? {})),
  };
  const result = await api.post<{ houses: HouseDto[]; hint: string }>(`/import-batches/${batchId}/confirm`, payload);
  return { houses: result.houses.map(houseFromDto), hint: result.hint };
}

// ---------------- 房源 / 偏好 ----------------

export async function listHouses(ws: string, status: 'active' | 'dropped' | 'all' = 'all'): Promise<House[]> {
  const rows = await api.get<HouseDto[]>(`/houses?workspace_id=${ws}&status=${status}`);
  return rows.map(houseFromDto);
}

export async function patchHouse(
  id: string,
  patch: Partial<Record<keyof House | 'dropReason' | 'status', unknown>>,
): Promise<House> {
  const body: Record<string, unknown> = {};
  const map: Record<string, string> = {
    name: 'name',
    region: 'region',
    address: 'address',
    rent: 'rent',
    deposit: 'deposit',
    agencyFee: 'agency_fee',
    propertyFee: 'property_fee',
    propertyBear: 'property_bear',
    netFee: 'net_fee',
    otherFee: 'other_fee',
    area: 'area',
    layout: 'layout',
    floor: 'floor',
    orientation: 'orientation',
    bathroom: 'bathroom',
    lighting: 'lighting',
    furniture: 'furniture',
    commuteMin: 'commute_min',
    commuteMode: 'commute_mode',
    metro: 'metro',
    nearby: 'nearby',
    pet: 'pet',
    shared: 'shared',
    sublet: 'sublet',
    maxPeople: 'max_people',
    leaseReq: 'lease_req',
    available: 'available',
    notes: 'notes',
    linkUrl: 'link_url',
    todos: 'todos',
    visits: 'visits',
    verify: 'verify',
    status: 'status',
    dropReason: 'drop_reason',
  };
  for (const [key, value] of Object.entries(patch)) {
    const target = map[key];
    if (target) body[target] = value;
  }
  const dto = await api.patch<HouseDto>(`/houses/${id}`, body);
  return houseFromDto(dto);
}

export async function createHouse(ws: string, house: House): Promise<House> {
  const dto = await api.post<HouseDto>(`/houses?workspace_id=${ws}`, houseToConfirm(house, '手动填写'));
  return houseFromDto(dto);
}

export async function deleteHouse(id: string): Promise<void> {
  await api.del<void>(`/houses/${id}`);
}

export async function getPreferences(ws: string): Promise<Preferences> {
  return prefsFromDto(await api.get<PreferenceDto>(`/preferences?workspace_id=${ws}`));
}

export async function putPreferences(ws: string, prefs: Preferences): Promise<Preferences> {
  return prefsFromDto(await api.put<PreferenceDto>(`/preferences?workspace_id=${ws}`, prefsToDto(prefs)));
}

// ---------------- 推荐 ----------------

export async function startRecommendation(ws: string, view: 'mix' | 'budget' | 'commute') {
  return api.post<{ recommendation_id: string; run_id: string }>('/recommendations', {
    workspace_id: ws,
    view,
  });
}

export function getRecommendation(id: string): Promise<RecommendationDto> {
  return api.get<RecommendationDto>(`/recommendations/${id}`);
}

// ---------------- 合同 ----------------

export async function saveContract(ws: string, text: string, houseId: string | null, name?: string) {
  return api.post<{ contract_id: string; run_id: string }>('/contracts', {
    workspace_id: ws,
    house_id: houseId,
    text,
    name,
  });
}

export async function uploadContract(ws: string, file: File, houseId: string | null) {
  const form = new FormData();
  form.append('workspace_id', ws);
  form.append('file', file);
  if (houseId) form.append('house_id', houseId);
  return api.post<{ contract_id: string; run_id: string }>('/contracts/upload', form);
}

export function listContracts(ws: string): Promise<ContractDto[]> {
  return api.get<ContractDto[]>(`/contracts?workspace_id=${ws}`);
}

export function getContract(id: string): Promise<ContractDto> {
  return api.get<ContractDto>(`/contracts/${id}`);
}

export function getContractText(id: string): Promise<{ contract_id: string; clauses: ClauseDto[] }> {
  return api.get(`/contracts/${id}/text`);
}

export function retryContract(id: string) {
  return api.post<{ contract_id: string; run_id: string }>(`/contracts/${id}/retry`);
}

export function deleteContract(id: string): Promise<void> {
  return api.del<void>(`/contracts/${id}`);
}

// ---------------- 核验 ----------------

export function startVerification(ws: string, houseId: string, contractId: string) {
  return api.post<{ verification_id: string; run_id: string }>('/verifications', {
    workspace_id: ws,
    house_id: houseId,
    contract_id: contractId,
  });
}

export function getVerification(id: string): Promise<VerificationDto> {
  return api.get<VerificationDto>(`/verifications/${id}`);
}

// ---------------- 对话 ----------------

export async function ensureConversation(ws: string, title?: string): Promise<string> {
  const conversation = await api.post<{ id: string }>('/conversations', { workspace_id: ws, title: title ?? '新对话' });
  return conversation.id;
}

export function listMessages(conversationId: string): Promise<MessageDto[]> {
  return api.get<MessageDto[]>(`/conversations/${conversationId}/messages`);
}

export function listConversations(ws: string): Promise<ConversationDto[]> {
  return api.get<ConversationDto[]>(`/conversations?workspace_id=${ws}`);
}

export function deleteConversation(conversationId: string): Promise<void> {
  return api.del<void>(`/conversations/${conversationId}`);
}

export function ask(
  conversationId: string,
  text: string,
  ctx: { houseId: string | null; contractId: string | null },
) {
  return api.post<{ message_id: string; run_id: string }>(`/conversations/${conversationId}/messages`, {
    text,
    house_id: ctx.houseId,
    contract_id: ctx.contractId,
  });
}

export function setContext(ws: string, houseId: string | null, contractId: string | null) {
  return api.put(`/workspaces/${ws}/ctx`, { house_id: houseId, contract_id: contractId });
}

export type { SubscribeOptions, RunEventDto, AnswerDto };
