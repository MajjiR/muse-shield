import { cn } from "@/lib/utils"
import type { MaskMode } from "@muse-shield/core"
import { Layers } from "lucide-react"

const NAMES: Record<string, string> = {
  medical: "Medical", legal: "Legal", mergers_acquisitions: "M&A", banking_finance: "Banking & finance", hr: "HR",
  insurance: "Insurance", real_estate: "Real estate", education: "Education", code: "Code", general: "General",
}

/** Classify mode: the document's categories and its one-line summary, under a message or preview. */
export function CategoryLine({ categories, summary, className }: { categories?: string[]; summary?: string; className?: string }) {
  if (!categories?.length) return null
  return (
    <div className={cn("flex max-w-full flex-wrap items-center gap-1.5 text-[12px] text-muted-foreground", className)}>
      <Layers className="size-3.5 shrink-0" aria-hidden />
      <span>Detected</span>
      {categories.map((c) => (
        <span key={c} className="rounded-[3px] border bg-card px-1.5 py-px text-foreground">{NAMES[c] ?? c}</span>
      ))}
      {summary && <span className="min-w-0 truncate" title={summary}>· {summary}</span>}
    </div>
  )
}

/** Normal: one call finds people, values and owners. Classify: also detects the document type and its extra private details. */
export function ModeToggle({ mode, onChange, disabled }: { mode: MaskMode; onChange: (m: MaskMode) => void; disabled?: boolean }) {
  return (
    <div role="radiogroup" aria-label="Masking mode" className="flex items-center rounded-md border p-0.5 text-[12px]">
      {(["normal", "classify"] as const).map((m) => (
        <button key={m} type="button" role="radio" aria-checked={mode === m} disabled={disabled} onClick={() => onChange(m)}
          title={m === "normal" ? "One call: people, values, owners" : "Also detects the document type (medical, legal, HR…) and masks its extra private details"}
          className={cn("rounded-[5px] px-2 py-0.5 transition-colors",
            mode === m ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground")}>
          {m === "normal" ? "Normal" : "Classify"}
        </button>
      ))}
    </div>
  )
}
