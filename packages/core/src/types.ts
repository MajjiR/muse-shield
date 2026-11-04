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
  /** A tool call Muse Spark planned: pending (waiting for you) or how it ended. */
  action: AgentAction | null;
}

export type ActionStatus = "pending" | "done" | "refused" | "denied" | "failed";

/** A tool call. `args` is what the model wrote (placeholders); `preview` holds the real values and never leaves this device. */
export interface AgentAction {
  action_id: string;
  chat_id: string;
  tool: string;
  status: ActionStatus;
  violations: string[];
  args: Record<string, unknown>;
  preview: Record<string, unknown>;
  /** What Muse Spark wrote, the contact it resolved through, and the real name and address (this device only). */
  recipients: { label: string; via: string; person: string | null; address: string }[];
  unmasked: string[];
  result: Record<string, unknown>;
  error: string;
  created_at: number;
}

export interface OutboxItem {
  id: string;
  chat_id: string;
  tool: string;
  payload: Record<string, unknown>;
  created_at: number;
}

export interface AuditChain {
  ok: boolean;
  entries?: number;
  head?: string;
  broken_at?: number;
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
  role: "user" | "assistant" | "reveal" | "tool_call" | "tool_result" | "document" | "image";
  masked_text: string;
  text: string;
  original: string | null;
  meta: { spans?: Span[]; cost_usd?: number | null; label?: string; level?: Level; decision?: "allow" | "deny"; tool?: string; status?: ActionStatus; action_id?: string };
  segments?: Segment[];
  /** role "document": the attached document, shown as a card. */
  document?: DocumentInfo | null;
  /** role "image": the attached masked image, shown as a card. */
  image?: ImageInfo | null;
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
  documents?: boolean;
  images?: boolean;
  images_off_reason?: string;
}

/** A covered part of an image: a value (kind "text", labelled with its vault placeholder) or a face, code, plate… */
export interface ImageRegion {
  kind: string;
  type: string;
  label: string;
  box: [number, number, number, number];
  source: string;
}

/** A masked image stored in a chat (POST /images). Only the masked picture is kept; values stay in the vault. */
export interface ImageInfo {
  image_id: string;
  chat_id: string;
  n: number;
  verified: boolean;
  counts: Record<string, number>;
  /** The original name: shown on this device only, never sent to a model. */
  filename: string;
  width: number;
  height: number;
  regions: ImageRegion[];
  masked_text: string;
  verify: { ok: boolean; leaked?: string[]; faces_left?: number; new_finds?: unknown[]; error?: string } | null;
  cost: { spark_usd?: number | null; sam_requests?: number };
  timings_ms: Record<string, number>;
  created_at: number;
}

export type DocumentFormat = "pdf" | "docx" | "pptx";
export type DocumentStatus = "extracting" | "analysing" | "verifying" | "ready" | "blocked" | "failed";

/** Something removed or flagged while masking a document, e.g. {code: "images_removed", count: 2, where: ["page 1"]}. */
export interface DocumentWarning {
  code: string;
  count?: number;
  where?: string[];
  labels?: string[];
}

export interface PageStatus {
  page: number;
  status: "ok" | "empty" | "scanned" | "unreadable" | "no_text";
}

export interface VerifyReport {
  ok: boolean;
  checks: number;
  failures: { label: string; where: string }[];
  warnings: DocumentWarning[];
}

export interface DocumentInfo {
  doc_id: string;
  chat_id: string;
  n: number;
  format: DocumentFormat;
  status: DocumentStatus;
  bytes: number;
  pages: number | null;
  counts: Record<string, number>;
  warnings: DocumentWarning[];
  page_status: PageStatus[];
  verify: VerifyReport | null;
  progress?: { done: number; total: number };
  /** The original name: shown on this device only, never sent to a model. */
  filename: string;
  has_masked_copy: boolean;
  error?: string | null;
  created_at: number;
}

/** With ?detail: the extracted text and its masked version, for the side-by-side preview (local only). */
export interface DocumentDetail extends DocumentInfo {
  text: string;
  masked_text: string;
  spans: Span[];
  units: [number, number, string][];
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
