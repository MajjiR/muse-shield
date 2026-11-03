import { looksLikeContext } from "@muse-shield/core"

/** One pastel per kind of detail. The placeholder's name also says the type, so colour is never the only cue. */
export type Tone = "person" | "org" | "amount" | "id" | "contact" | "place" | "date" | "context"

const BY_TYPE: Record<string, Tone> = {
  PERSON: "person", ORG: "org", PROJECT: "org", AMOUNT: "amount", ID: "id", SECRET: "id", SENSITIVE_ATTRIBUTE: "id",
  CONTACT: "contact", ADDRESS: "place", LOCATION: "place", DATE: "date",
}
const AMOUNT_ROLES = new Set(["SALARY", "PRICE", "DEAL_VALUE", "LOAN", "REVENUE", "BUDGET", "FEE", "AMOUNT"])

export function toneForType(type: string, kind?: string): Tone {
  if (kind === "context") return "context"
  return BY_TYPE[type] ?? (AMOUNT_ROLES.has(type) ? "amount" : "id")
}

/** Tone from a placeholder alone, e.g. <SALARY_1> -> amount, <DEAL_1> -> context. */
export function toneForLabel(label: string, kind?: string): Tone {
  if (kind === "context" || (kind == null && looksLikeContext(label))) return "context"
  return toneForType(label.replace(/^<|_\d+>$/g, ""))
}

export const toneVars = (t: Tone) => ({ bg: `var(--pii-${t})`, line: `var(--pii-${t}-line)`, ink: `var(--pii-${t}-ink)` })
