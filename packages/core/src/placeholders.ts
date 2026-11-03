// Placeholder helpers shared by every client.
export const LABEL_RE = /<[A-Z][A-Z_]*_\d+>/g;
export const CONTEXT_KINDS = new Set(["DEAL", "DECISION", "PLAN", "NEGOTIATION", "PROJECT", "HR"]);

export interface Piece {
  text: string;
  label?: string;
}

/** Split masked text into plain runs and placeholder labels. */
export function splitLabels(text: string): Piece[] {
  const out: Piece[] = [];
  let cursor = 0;
  for (const m of text.matchAll(LABEL_RE)) {
    if (m.index! > cursor) out.push({ text: text.slice(cursor, m.index) });
    out.push({ text: m[0], label: m[0] });
    cursor = m.index! + m[0].length;
  }
  if (cursor < text.length) out.push({ text: text.slice(cursor) });
  return out;
}

/** Best guess when only the label is known (PROJECT is ambiguous: an entity or a context block). */
export function looksLikeContext(label: string): boolean {
  return CONTEXT_KINDS.has(label.replace(/^<|_\d+>$/g, "")) && !label.startsWith("<PROJECT_");
}
