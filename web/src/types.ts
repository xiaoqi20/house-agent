import type { ChatReply, RiskView, RisksSummary } from "@/api/model";

export type MsgRole = "user" | "ai";
export type MsgKind =
  "text" | "file" | "files" | "typing" | "progress" | "report";

/** pending = 前端预置的灰圈，等后端 SSE 推到 active/done 再点亮 */
export interface Step {
  index: number;
  label: string;
  status: "pending" | "active" | "done";
}

export interface ChatMsg {
  id: string;
  role: MsgRole;
  kind: MsgKind;
  text?: string;
  contractId?: number;
  mime?: string;
  steps?: Step[];
  files?: { name: string; contractId: number; mime: string }[];
  report?: RisksSummary;
  answer?: ChatReply;
}

export type { ChatReply, RiskView, RisksSummary };
