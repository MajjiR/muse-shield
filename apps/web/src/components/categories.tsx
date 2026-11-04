import { modeShort } from "@/lib/modes"
import { cn } from "@/lib/utils"
import type { MaskMode, ModeInfo } from "@muse-shield/core"
import { Layers, Lock } from "lucide-react"

const NAMES: Record<string, string> = {
  medical: "Medical", legal: "Legal", mergers_acquisitions: "M&A", banking_finance: "Banking & finance", hr: "HR",
  insurance: "Insurance", real_estate: "Real estate", education: "Education", code: "Code", general: "General",
}
/** Entity resolution + classify: the document's categories and its one-line summary, under a message or preview. */
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

/** New chat: pick the masking mode. The chat stays in it; another mode means another chat. */
export function ModePicker({ modes, value, onChange, disabled }: { modes: ModeInfo[]; value: MaskMode; onChange: (m: MaskMode) => void; disabled?: boolean }) {
  return (
    <div role="radiogroup" aria-label="Masking mode for this new chat" className="flex flex-wrap items-center gap-1 rounded-md border p-0.5 text-[12px]">
      {modes.map((m) => (
        <button key={m.id} type="button" role="radio" aria-checked={value === m.id} disabled={disabled} onClick={() => onChange(m.id)}
          title={m.detail}
          className={cn("rounded-[5px] px-2 py-0.5 transition-colors",
            value === m.id ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground")}>
          {m.label}
        </button>
      ))}
    </div>
  )
}

/** An existing chat: its mode, locked. */
export function ModeBadge({ mode, modes }: { mode?: MaskMode | null; modes: ModeInfo[] }) {
  if (!mode) return null
  const info = modes.find((m) => m.id === mode)
  return (
    <span title={`${info?.detail ?? mode}. Start a new chat to use another mode.`}
      className="flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md border px-2 py-0.5 text-[12px] text-muted-foreground">
      <Lock className="size-3" aria-hidden /> {modeShort(mode)}
    </span>
  )
}
