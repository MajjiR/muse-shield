// Mirrors CONTRACT.md. Keep in sync with muse_shield/app/schemas.py.

export type SpanKind = "entity" | "context";
export type Level = "shape" | "summary" | "full";

export interface Span {
  start: number;
  end: number;
  text?: string; // present in live /mask responses; never stored
  type: string;
  role?: string | null;
  placeholder: string;
  kind: SpanKind;
  source: "model" | "policy" | "user";
  in_context?: string | null;
}

export interface ContextBlock {
  label: string;
  kind: string;
  subtype?: string | null;
  start: number;
  end: number;
  summary: string;
}

export interface MaskResult {
  chat_id: string;
  masked_text: string;
  spans: Span[];
  contexts: ContextBlock[];
  analysis_ok: boolean;
  error: string;
  latency_ms: number;
  cost_usd: number | null;
  mask_id: string | null;
}

export interface Ask {
  ask_id: string;
  chat_id: string;
  label: string;
  kind: "entity" | "context";
  level: Level;
  reason: string;
  preview: string;
  previews: Partial<Record<Level, string>>;
}

export interface Turn {
  chat_id: string;
  message_id: string;
  reply: string;
  masked_reply: string;
  sent: { role: string; content: string }[];
  ask: Ask | null;
  masked: MaskResult | null;
  error: string;
  cost_usd: number;
  unknown_labels: string[];
}

export interface Segment {
  text: string;
  label?: string;
  kind?: "entity" | "context" | "unknown";
  /** Assistant replies only, context blocks: the real passage; `text` is then its one-line summary. */
  full?: string;
}

export interface Message {
  message_id: string;
  role: "user" | "assistant" | "reveal";
  masked_text: string;
  text: string;
  original: string | null;
  meta: { spans?: Span[]; cost_usd?: number | null; label?: string; level?: Level; decision?: "allow" | "deny" };
  segments?: Segment[];
  created_at: number;
}

export interface ChatSummary {
  chat_id: string;
  title: string;
  created_at: number;
  messages: number;
}

export interface ChatDetail {
  chat_id: string;
  messages: Message[];
  consents: { ts: number; label: string; level: Level; decision: "allow" | "deny"; reason: string }[];
}

export interface Health {
  ok: boolean;
  version: string;
  analysis: boolean;
  chat: boolean;
  analysis_model: string | null;
  chat_model: string | null;
  analysis_off_reason: string;
  chat_off_reason: string;
}

export interface VaultItems {
  entities: { label: string; type: string; base: string; entity_id: string; chats: number }[];
  contexts: { label: string; kind: string; subtype: string | null; summary: string }[];
}

export interface Graph {
  nodes: { id: string; group: "entity" | "context"; type: string; chats?: number; summary?: string }[];
  edges: { source: string; target: string; rel: "appears_with" | "mentioned_in"; weight: number }[];
}

export interface Metrics {
  masked_by_type: Record<string, number>;
  asks: number;
  consents: { allow: number; deny: number };
  cost_by_chat: Record<string, number>;
  cost_total: number;
  inspector: { requests: number; analysis_requests: number; chat_requests: number; bytes_sent: number };
}

export interface InspectorRecord {
  id: string;
  ts: number;
  purpose: "analysis" | "chat";
  chat_id: string | null;
  url: string;
  bytes: number;
  status: number;
  latency_ms: number;
  request_body: string;
  response_body: string;
  usage: Record<string, unknown>;
}

export interface LeakAudit {
  chat_requests_scanned: number;
  checks: number;
  leaks: { request: string; chat_id: string; labels: string[] }[];
  clean: boolean;
}
