// Engine API client: plain fetch, so it works in the browser, Electron and React Native.
import type { Ask, ChatDetail, ChatSummary, Graph, Health, InspectorRecord, LeakAudit, Level, MaskResult, Metrics, Turn, VaultItems } from "./types";

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
  return {
    health: () => call<Health>("/health"),
    mask: (text: string, chatId?: string | null) => call<MaskResult>("/mask", { text, chat_id: chatId ?? null }),
    unmask: (text: string, chatId: string) => call<{ text: string; unknown: string[] }>("/unmask", { text, chat_id: chatId }),
    chat: (message: string, chatId?: string | null, maskId?: string | null) =>
      call<Turn>("/chat", { message, chat_id: chatId ?? null, mask_id: maskId ?? null }),
    reveal: (ask: Ask, decision: "allow" | "deny", level?: Level) => call<Turn>("/reveal", { ask_id: ask.ask_id, decision, level }),
    chats: () => call<ChatSummary[]>("/chats"),
    chatDetail: (chatId: string) => call<ChatDetail>(`/chats/${chatId}`),
    vault: (chatId: string) => call<VaultItems>(`/chats/${chatId}/vault`),
    vaultReveal: (chatId: string, label: string) => call<{ label: string; value: string }>("/vault/reveal", { chat_id: chatId, label }),
    graph: (chatId: string) => call<Graph>(`/chats/${chatId}/graph`),
    inspector: () => call<{ summary: Metrics["inspector"]; requests: InspectorRecord[] }>("/inspector"),
    audit: () => call<LeakAudit>("/inspector/audit"),
    metrics: () => call<Metrics>("/metrics"),
  };
}

export type Engine = ReturnType<typeof createEngine>;
