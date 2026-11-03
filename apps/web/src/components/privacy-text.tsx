import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { looksLikeContext, splitLabels, type Segment, type Span } from "@muse-shield/core"
import type { ReactNode } from "react"

function Tip({ tip, children }: { tip: string; children: React.ReactElement }) {
  return (
    <Tooltip>
      <TooltipTrigger render={children} />
      <TooltipContent className="font-mono text-xs">{tip}</TooltipContent>
    </Tooltip>
  )
}

/** A placeholder as the model sees it. */
export function Chip({ label, context, tip }: { label: string; context?: boolean; tip?: string }) {
  return (
    <Tip tip={tip ?? (context ? "hidden context block" : "masked value")}>
      <span
        className={cn(
          "rounded-[5px] border px-1 font-mono text-[11.5px] whitespace-nowrap",
          context ? "border-context-line bg-context" : "border-masked-line bg-masked",
        )}
      >
        {label}
      </span>
    </Tip>
  )
}

/** Masked text with every placeholder shown as a chip. */
export function MaskedText({ text, kinds = {} }: { text: string; kinds?: Record<string, string> }) {
  return (
    <>
      {splitLabels(text).map((p, i) =>
        p.label ? (
          <Chip key={i} label={p.label} context={(kinds[p.label] ?? (looksLikeContext(p.label) ? "context" : "entity")) === "context"} />
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </>
  )
}

/** The user's original text: masked entities in green, context blocks in blue (entities nested inside). */
export function OriginalText({ text, spans = [] }: { text: string; spans?: Span[] }) {
  const ents = spans.filter((s) => s.kind !== "context").sort((a, b) => a.start - b.start)
  const ctxs = spans.filter((s) => s.kind === "context").sort((a, b) => a.start - b.start)
  const run = (from: number, to: number, keyBase: string): ReactNode[] => {
    const out: ReactNode[] = []
    let cur = from
    for (const e of ents) {
      if (e.start < from || e.end > to) continue
      if (e.start > cur) out.push(text.slice(cur, e.start))
      out.push(
        <Tip key={`${keyBase}-${e.start}`} tip={`${e.type}${e.role ? ` · ${e.role}` : ""} → ${e.placeholder}`}>
          <mark className="rounded-[4px] bg-masked px-0.5 text-inherit shadow-[inset_0_-2px_0_var(--masked-line)]">
            {text.slice(e.start, e.end)}
          </mark>
        </Tip>,
      )
      cur = e.end
    }
    if (to > cur) out.push(text.slice(cur, to))
    return out
  }
  const out: ReactNode[] = []
  let cur = 0
  for (const c of ctxs) {
    out.push(...run(cur, c.start, `r${cur}`))
    out.push(
      <Tip key={`c${c.start}`} tip={`${c.type} block → ${c.placeholder}`}>
        <mark className="rounded-[4px] bg-context px-1 py-px text-inherit shadow-[inset_2px_0_0_var(--context-line)]">
          {run(c.start, c.end, `c${c.start}`)}
        </mark>
      </Tip>,
    )
    cur = c.end
  }
  out.push(...run(cur, text.length, `r${cur}`))
  return <>{out}</>
}

/** An assistant reply after local rehydration: restored values in green, restored passages collapsible. */
export function RestoredText({ segments = [] }: { segments?: Segment[] }) {
  return (
    <>
      {segments.map((s, i) => {
        if (!s.label) return <span key={i}>{s.text}</span>
        if (s.kind === "context") {
          return (
            <Collapsible key={i} className="inline">
              <CollapsibleTrigger className="cursor-pointer">
                <Chip label={s.label} context tip="restored from your vault: click to show" />
              </CollapsibleTrigger>
              <CollapsibleContent className="my-1.5 block rounded-r-lg border-l-[3px] border-context-line bg-context px-2.5 py-2">
                {s.text}
              </CollapsibleContent>
            </Collapsible>
          )
        }
        if (s.kind === "unknown") return <Chip key={i} label={s.label} tip="not in your vault: the model invented this placeholder" />
        return (
          <Tip key={i} tip={`${s.label} restored on this device`}>
            <mark className="rounded-[4px] bg-masked px-0.5 text-inherit shadow-[inset_0_-1px_0_var(--masked-line)]">{s.text}</mark>
          </Tip>
        )
      })}
    </>
  )
}
