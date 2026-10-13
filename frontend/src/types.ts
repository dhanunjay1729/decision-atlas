export type EvidenceStatus =
  "supported" | "contradicted" | "insufficient" | "value";
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
}
export interface Argument {
  agent: number;
  round: number;
  position: string;
  body: string;
  claim_ids: string[];
  challenges: string[];
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
}
export interface Setup {
  question: string;
  perspectives: string[];
  document_text: string;
  include_web: boolean;
  sources: Source[];
}
