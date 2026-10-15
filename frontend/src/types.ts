export type EvidenceStatus =
  "supported" | "contradicted" | "insufficient" | "value" | "unverified" | "review";
export interface Source {
  id: string;
  title: string;
  text: string;
  url?: string;
  page?: number;
  kind: "document" | "web" | "sample";
}
export interface Claim {
  id: string;
  agent: number;
  text: string;
  status: EvidenceStatus;
  source_ids: string[];
  explanation: string;
  assessments?: {reviewer: string; status: EvidenceStatus; explanation: string; source_ids: string[]}[];
}
export interface Argument {
  agent: number;
  round: number;
  position: string;
  body: string;
  claim_ids: string[];
  challenges: string[];
  model?: string | null;
}
export interface Analysis {
  question: string;
  perspectives: string[];
  sources: Source[];
  claims: Claim[];
  arguments: Argument[];
  report: string;
  mode: "sample" | "live";
  model?: string;
  accounted_usd?: number;
  publish_token?: string;
  published?: boolean;
  evidence_mode?: "web" | "documents" | "knowledge";
}
export interface Setup {
  question: string;
  perspectives: string[];
  document_text: string;
  include_web: boolean;
  sources: Source[];
}
