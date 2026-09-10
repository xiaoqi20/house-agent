/** 后端 DTO（snake_case，与 server/src/rentgraph/schemas 一致）。 */

export type SourceKey = 'paste' | 'manual' | 'batch' | 'file-xlsx' | 'file-docx' | 'file-txt' | 'link';

export interface HouseDto {
  id: string;
  no: string;
  batch_id: string | null;
  status: 'active' | 'dropped';
  drop_reason: string;
  source: SourceKey;
  raw: string;
  name: string;
  region: string;
  address: string;
  rent: number | null;
  deposit: string | null;
  agency_fee: number | null;
  property_fee: number | null;
  property_bear: string;
  net_fee: number | null;
  other_fee: string | number | null;
  area: number | null;
  layout: string;
  floor: string;
  orientation: string;
  bathroom: boolean | null;
  lighting: string;
  furniture: string;
  commute_min: number | null;
  commute_mode: string;
  metro: string;
  nearby: string;
  pet: string;
  shared: boolean;
  sublet: string;
  max_people: number | null;
  lease_req: string;
  available: string;
  notes: string;
  visits: Array<{ time: string; text: string }>;
  todos: string[];
  verify: string[];
  contract_id: string | null;
  link_url: string;
  source_label: string;
  completeness: number;
  missing: string[];
  evidence: Record<string, string>;
}

export interface HouseDraftDto extends Omit<HouseDto, 'id' | 'no' | 'status' | 'batch_id' | 'todos' | 'visits' | 'contract_id'> {
  draft_id: string;
  confidence: number;
  duplicate_of: string | null;
}

export interface BatchDto {
  id: string;
  workspace_id: string;
  source: string;
  status: string;
  filename: string | null;
  link_url: string | null;
  raw_text: string | null;
  drafts: HouseDraftDto[];
  house_count: number;
  error: { code?: string; message?: string; hint?: string } | null;
  run_id: string | null;
}

export interface PreferenceDto {
  version: number;
  budget: number | null;
  commute: number | null;
  need_bathroom: boolean;
  allow_shared: boolean;
  soft: { south: boolean; light: boolean; high_floor: boolean; big_area: boolean; flex_pay: boolean };
}

export interface RankItemDto {
  house_id: string;
  rank: number;
  monthly_cost: number;
  monthly_cost_unknown: string[];
  one_time_cost: number;
  one_time_label: string;
  hard_violations: string[];
  soft_hits: string[];
  soft_miss: string[];
  verdict: '优先考虑' | '可作为备选' | '不建议';
  comparable: boolean;
  tie_break_note: string;
}

export interface ExplanationDto {
  why: string[];
  tradeoffs: string[];
  risks: string[];
  todos: string[];
  next: string[];
}

export interface RecommendationDto {
  id: string;
  prefs_version: number;
  view: 'mix' | 'budget' | 'commute';
  created_at: string | null;
  snapshot: { houses: HouseDto[]; prefs: PreferenceDto };
  views: Record<'budget' | 'commute' | 'mix', { order: string[]; items: Record<string, RankItemDto> }>;
  explanation: Record<string, ExplanationDto>;
  about: { hard_rules?: string[]; soft_rules?: string[]; missing?: string[]; window?: { count: number; ok: boolean; message: string } };
}

export interface ClauseRiskDto {
  id: string;
  level: 'high' | 'medium' | 'low';
  title: string;
  reason: string;
  suggestion: string;
  negotiation_script: string | null;
}

export interface ContractDto {
  id: string;
  no: string;
  name: string;
  source: string;
  time: string;
  status: 'uploaded' | 'parsing' | 'analyzing' | 'done' | 'failed';
  reason: string;
  size: string;
  bound_house_id: string | null;
  clauses_list: Array<[number | null, string, string]>;
  risk_clauses: number[];
  negotiation: string;
  health_score: number | null;
  page_count: number;
}

export interface ClauseDto {
  id: string;
  clause_no: number | null;
  clause_type: string;
  title: string;
  raw_text: string;
  page: number | null;
  char_start: number | null;
  char_end: number | null;
  is_risk: boolean;
  risks: ClauseRiskDto[];
}

export interface VerificationItemDto {
  id: string;
  claim: string;
  field: string;
  anchor: string | null;
  clause_id: string | null;
  clause_no: number | null;
  clause_text: string;
  page: number | null;
  char_start: number | null;
  char_end: number | null;
  result: '一致' | '冲突' | '未约定' | '无法判断';
  advice: string;
  severity: 'high' | 'medium' | 'low' | null;
  reason: string;
}

export interface VerificationDto {
  id: string;
  house_id: string;
  contract_id: string;
  status: string;
  summary: Record<string, unknown>;
  items: VerificationItemDto[];
  negotiation: string;
  error: string | null;
  run_id: string | null;
}

export interface AnswerDto {
  message_id: string;
  mode: 'context' | 'house_only' | 'general' | 'refusal' | 'out_of_scope';
  html: string;
  citations: Array<{ clause_id: string | null; clause_no: number | null; label: string; contract_id: string | null; page: number | null }>;
  followups: string[];
  sources: string[];
}

export interface MessageDto {
  id: string;
  role: 'user' | 'ai';
  content: { text?: string; html?: string; mode?: string; followups?: string[]; sources?: string[] };
  citations: AnswerDto['citations'];
  created_at: string | null;
}

export interface ConversationDto {
  id: string;
  workspace_id: string;
  title: string;
  created_at: string | null;
  message_count: number;
}

export interface RunEventDto {
  event_id: string;
  type: 'progress' | 'token' | 'interrupt' | 'done' | 'error' | 'cancelled';
  run_id: string;
  workspace_id: string | null;
  thread_id: string | null;
  house_id: string | null;
  contract_id: string | null;
  seq: number;
  data: {
    step?: string;
    index?: number;
    label?: string;
    status?: string;
    detail?: string;
    text?: string;
    code?: string;
    message?: string;
    hint?: string;
    reason?: string;
    result?: unknown;
    [key: string]: unknown;
  };
}

export interface WorkspaceDto {
  id: string;
  title: string;
  created_at: string;
  expires_at: string;
  house_count: number;
  contract_count: number;
  ctx_house_id: string | null;
  ctx_contract_id: string | null;
}
