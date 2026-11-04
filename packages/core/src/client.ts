// Engine API client: plain fetch, so it works in the browser, Electron and React Native.
import type { AgentAction, Ask, AuditChain, ChatDetail, ChatSummary, DocumentDetail, DocumentInfo, Graph, ImageInfo, Health, InspectorRecord, LeakAudit, Level, MaskMode, MaskResult, Metrics, OutboxItem, Turn, VaultItems } from "./types";

export class EngineError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export function createEngine(baseUrl = "") {
  async function call<T>(path: string, body?: unknown): Promise<T> {
    const r = await fetch(baseUrl + path, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new EngineError((data as { detail?: string }).detail ?? r.statusText, r.status);
    return data as T;
  }
  async function upload<T>(path: string, file: Blob & { name?: string }, chatId?: string | null): Promise<T> {
    const headers: Record<string, string> = { "content-type": "application/octet-stream", "x-filename": encodeURIComponent(file.name ?? "file") };
    if (chatId) headers["x-chat-id"] = chatId;
    const r = await fetch(baseUrl + path, { method: "POST", headers, body: file });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new EngineError((data as { detail?: string }).detail ?? r.statusText, r.status);
    return data as T;
  }
  return {
    health: () => call<Health>("/health"),
    /** `mode` applies to a new chat only; an existing chat keeps the mode it's locked to. */
    mask: (text: string, chatId?: string | null, mode?: MaskMode | null) => call<MaskResult>("/mask", { text, chat_id: chatId ?? null, mode: mode ?? null }),
    unmask: (text: string, chatId: string) => call<{ text: string; unknown: string[] }>("/unmask", { text, chat_id: chatId }),
    chat: (message: string, chatId?: string | null, maskId?: string | null, documentIds: string[] = [], imageIds: string[] = []) =>
      call<Turn>("/chat", { message, chat_id: chatId ?? null, mask_id: maskId ?? null, document_ids: documentIds, image_ids: imageIds }),
    reveal: (ask: Ask, decision: "allow" | "deny", level?: Level) => call<Turn>("/reveal", { ask_id: ask.ask_id, decision, level }),
    chats: () => call<ChatSummary[]>("/chats"),
    newChat: (mode?: MaskMode | null) => call<{ chat_id: string; mode: MaskMode | null }>("/chats", { mode: mode ?? null }),
    chatDetail: (chatId: string) => call<ChatDetail>(`/chats/${chatId}`),
    vault: (chatId: string) => call<VaultItems>(`/chats/${chatId}/vault`),
    vaultReveal: (chatId: string, label: string) => call<{ label: string; value: string }>("/vault/reveal", { chat_id: chatId, label }),
    graph: (chatId: string) => call<Graph>(`/chats/${chatId}/graph`),
    inspector: () => call<{ summary: Metrics["inspector"]; requests: InspectorRecord[] }>("/inspector"),
    audit: () => call<LeakAudit>("/inspector/audit"),
    metrics: () => call<Metrics>("/metrics"),
    actions: (chatId: string) => call<AgentAction[]>(`/chats/${chatId}/actions`),
    /** Runs the action on this device; for a call Muse Spark planned, the reply comes back as a Turn. */
    decideAction: (actionId: string, decision: "confirm" | "deny") => call<Turn>(`/agent/actions/${actionId}/${decision}`, {}),
    outbox: (chatId: string) => call<OutboxItem[]>(`/chats/${chatId}/outbox`),
    auditChain: () => call<AuditChain>("/vault/audit/verify"),
    /** Upload a PDF, .docx or .pptx into a chat (a new one if chatId is empty). The raw bytes go to the local engine only. */
    uploadDocument: (file: Blob & { name?: string }, chatId?: string | null) => upload<DocumentInfo>("/documents", file, chatId),
    /** Mask an image (faces blurred, values covered) and keep the masked copy in the chat. Takes ~20-30 s. */
    uploadImage: (file: Blob & { name?: string }, chatId?: string | null) => upload<ImageInfo>("/images", file, chatId),
    image: (imageId: string) => call<ImageInfo>(`/images/${imageId}`),
    /** URL of the masked PNG (served by the local engine). */
    maskedImageUrl: (imageId: string, download = false) => `${baseUrl}/images/${imageId}/masked${download ? "?download=true" : ""}`,
    document: (docId: string) => call<DocumentInfo>(`/documents/${docId}`),
    documentDetail: (docId: string) => call<DocumentDetail>(`/documents/${docId}?detail=true`),
    chatDocuments: (chatId: string) => call<DocumentInfo[]>(`/chats/${chatId}/documents`),
    deleteDocument: (docId: string) => call<{ ok: boolean }>(`/documents/${docId}/delete`, {}),
    deleteImage: (imageId: string) => call<{ ok: boolean }>(`/images/${imageId}/delete`, {}),
    /** Deletes the chat and everything in it (messages, files, images, hidden values only it used). */
    deleteChat: (chatId: string) => call<{ ok: boolean; removed: Record<string, number> }>(`/chats/${chatId}/delete`, {}),
    /** The verified masked copy, with the download name the engine chose. */
    downloadMasked: async (docId: string) => {
      const r = await fetch(`${baseUrl}/documents/${docId}/masked`);
      if (!r.ok) throw new EngineError((await r.json().catch(() => ({})) as { detail?: string }).detail ?? r.statusText, r.status);
      const cd = r.headers.get("content-disposition") ?? "";
      const name = decodeURIComponent(/filename\*=UTF-8''([^;]+)/.exec(cd)?.[1] ?? "document.masked");
      return { blob: await r.blob(), name };
    },
  };
}

export type Engine = ReturnType<typeof createEngine>;
