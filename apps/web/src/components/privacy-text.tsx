import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { looksLikeContext, splitLabels, type Segment, type Span } from "@muse-shield/core"
import { ChevronRight } from "lucide-react"
import type { ReactNode } from "react"

function Tip({ tip, children }: { tip: ReactNode; children: React.ReactElement }) {
  return (
    <Tooltip>
      <TooltipTrigger render={children} />
      <TooltipContent className="max-w-xs text-xs leading-snug">{tip}</TooltipContent>
    </Tooltip>
  )
}

/** A placeholder exactly as the model sees it. */
export function Chip({ label, context, tip, size = "sm" }: { label: string; context?: boolean; tip?: ReactNode; size?: "xs" | "sm" }) {
  return (
    <Tip tip={tip ?? (context ? "A hidden passage, kept in your vault" : "A hidden value, kept in your vault")}>
      <span
        className={cn(
          "inline-flex items-center rounded-md border font-mono font-medium whitespace-nowrap align-baseline",
          size === "xs" ? "px-1 py-px text-[10.5px]" : "px-1.5 py-px text-[11.5px]",
          context ? "border-foreground bg-foreground text-background" : "border-foreground/25 bg-card text-foreground",
        )}
      >
        {label}
      </span>
    </Tip>
  )
}

/** Masked text with every placeholder rendered as a chip (or, with plain, as quiet monospace text for titles). */
export function MaskedText({ text, kinds = {}, size, plain }: { text: string; kinds?: Record<string, string>; size?: "xs" | "sm"; plain?: boolean }) {
  if (plain) {
    return (
      <>
        {splitLabels(text).map((p, i) =>
          p.label ? <span key={i} className="font-mono text-[0.9em] text-muted-foreground">{p.label}</span> : <span key={i}>{p.text}</span>,
        )}
      </>
    )
  }
  return (
    <>
      {splitLabels(text).map((p, i) =>
        p.label ? (
          <Chip key={i} size={size} label={p.label}
            context={(kinds[p.label] ?? (looksLikeContext(p.label) ? "context" : "entity")) === "context"} />
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </>
  )
}

const markEntity = "rounded-[2px] bg-masked px-0.5 text-inherit underline decoration-foreground/45 decoration-[1.5px] underline-offset-[3px]"
const markContext = "rounded-[2px] bg-context px-1 py-0.5 text-inherit box-decoration-clone shadow-[inset_2px_0_0_var(--context-line)]"

/** The user's own words: masked values underlined in green, context blocks shaded blue (entities nested inside). */
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
        <Tip key={`${keyBase}-${e.start}`} tip={<TipBody kind={e.type} role={e.role} label={e.placeholder} />}>
          <mark className={markEntity}>{text.slice(e.start, e.end)}</mark>
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
      <Tip key={`c${c.start}`} tip={<TipBody kind={`${c.type} passage`} label={c.placeholder} />}>
        <mark className={markContext}>{run(c.start, c.end, `c${c.start}`)}</mark>
      </Tip>,
    )
    cur = c.end
  }
  out.push(...run(cur, text.length, `r${cur}`))
  return <>{out}</>
}

function TipBody({ kind, role, label }: { kind: string; role?: string | null; label: string }) {
  return (
    <span className="flex flex-col gap-0.5">
      <span className="font-medium">{kind.replace(/_/g, " ").toLowerCase()}{role ? ` · ${role.replace(/_/g, " ").toLowerCase()}` : ""}</span>
      <span className="opacity-75">Sent as <span className="font-mono">{label}</span></span>
    </span>
  )
}

/** A reply after rehydration on this device: restored values in green, restored passages collapsible. */
export function RestoredText({ segments = [] }: { segments?: Segment[] }) {
  return (
    <>
      {segments.map((s, i) => {
        if (!s.label) return <span key={i}>{s.text}</span>
        if (s.kind === "context") {
          return (
            <Collapsible key={i} className="inline">
              <CollapsibleTrigger className="group inline-flex cursor-pointer items-center gap-0.5 align-baseline">
                <ChevronRight className="size-3 text-muted-foreground transition-transform group-data-[panel-open]:rotate-90" aria-hidden />
                <Chip label={s.label} context tip="Restored from your vault. Click to read it." />
              </CollapsibleTrigger>
              <CollapsibleContent className="my-2 block border-l-2 border-foreground bg-muted px-3 py-2 text-[13.5px]">
                {s.text}
              </CollapsibleContent>
            </Collapsible>
          )
        }
        if (s.kind === "unknown") {
          return <Chip key={i} label={s.label} tip="Not in your vault: the model made this placeholder up." />
        }
        return (
          <Tip key={i} tip={<>Restored on this device from <span className="font-mono">{s.label}</span></>}>
            <mark className="rounded-[2px] bg-masked px-0.5 text-inherit underline decoration-foreground/30 decoration-dotted underline-offset-[3px]">{s.text}</mark>
          </Tip>
        )
      })}
    </>
  )
}
