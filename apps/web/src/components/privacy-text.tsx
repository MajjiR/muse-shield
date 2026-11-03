import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { toneForLabel, toneForType, toneVars } from "@/lib/tones"
import { looksLikeContext, splitLabels, type Segment, type Span } from "@muse-shield/core"
import { ChevronRight } from "lucide-react"
import type { CSSProperties, ReactNode } from "react"

function Tip({ tip, children }: { tip: ReactNode; children: React.ReactElement }) {
  return (
    <Tooltip>
      <TooltipTrigger render={children} />
      <TooltipContent className="max-w-xs text-xs leading-snug">{tip}</TooltipContent>
    </Tooltip>
  )
}

/** A placeholder exactly as the model sees it, tinted by its type. */
export function Chip({ label, context, tip, size = "sm" }: { label: string; context?: boolean; tip?: ReactNode; size?: "xs" | "sm" }) {
  const v = toneVars(toneForLabel(label, context ? "context" : "entity"))
  return (
    <Tip tip={tip ?? (context ? "A hidden passage, kept in your vault" : "A hidden value, kept in your vault")}>
      <span
        style={{ background: v.bg, borderColor: v.line, color: v.ink }}
        className={cn(
          "inline-flex items-center rounded-[3px] border font-mono font-medium whitespace-nowrap align-baseline",
          size === "xs" ? "px-1 py-px text-[11px]" : "px-1.5 py-px text-[12px]",
        )}
      >
        {label}
      </span>
    </Tip>
  )
}

/** Masked text with every placeholder as a chip (or, with plain, as quiet monospace text for titles). */
export function MaskedText({ text, kinds = {}, size, plain }: { text: string; kinds?: Record<string, string>; size?: "xs" | "sm"; plain?: boolean }) {
  return (
    <>
      {splitLabels(text).map((p, i) => {
        if (!p.label) return <span key={i}>{p.text}</span>
        if (plain) return <span key={i} className="font-mono text-[0.88em] text-muted-foreground">{p.label}</span>
        const ctx = (kinds[p.label] ?? (looksLikeContext(p.label) ? "context" : "entity")) === "context"
        return <Chip key={i} size={size} label={p.label} context={ctx} />
      })}
    </>
  )
}

/**
 * The user's own words with what was masked highlighted in its type's pastel. With animate, each item
 * lights up in reading order (passages first), as the analysis result arrives.
 */
export function OriginalText({ text, spans = [], animate }: { text: string; spans?: Span[]; animate?: boolean }) {
  const ents = spans.filter((s) => s.kind !== "context").sort((a, b) => a.start - b.start)
  const ctxs = spans.filter((s) => s.kind === "context").sort((a, b) => a.start - b.start)
  let order = 0
  const reveal = (line: string): { className: string; style: CSSProperties } =>
    animate
      ? { className: "ms-mark-in", style: { ["--ms-delay" as string]: `${order++ * 110}ms`, ["--ms-glow" as string]: `color-mix(in srgb, ${line} 45%, transparent)` } }
      : { className: "", style: {} }

  const run = (from: number, to: number, keyBase: string): ReactNode[] => {
    const out: ReactNode[] = []
    let cur = from
    for (const e of ents) {
      if (e.start < from || e.end > to) continue
      if (e.start > cur) out.push(text.slice(cur, e.start))
      const v = toneVars(toneForType(e.role && e.role !== "OTHER" ? e.role : e.type))
      const r = reveal(v.line)
      out.push(
        <Tip key={`${keyBase}-${e.start}`} tip={<TipBody kind={e.type} role={e.role} label={e.placeholder} />}>
          <mark
            className={cn("rounded-[3px] px-0.5 text-inherit underline decoration-[1.5px] underline-offset-[3px]", r.className)}
            style={{ background: v.bg, textDecorationColor: v.line, ...r.style }}
          >
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
    const v = toneVars("context")
    const r = reveal(v.line)
    out.push(
      <Tip key={`c${c.start}`} tip={<TipBody kind={`${c.type} passage`} label={c.placeholder} />}>
        <mark
          className={cn("rounded-[3px] px-1 py-0.5 text-inherit box-decoration-clone", r.className)}
          style={{ background: v.bg, boxShadow: `inset 2px 0 0 ${v.line}`, ...r.style }}
        >
          {run(c.start, c.end, `c${c.start}`)}
        </mark>
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
      <span className="font-medium">{kind.replace(/_/g, " ").toLowerCase()}{role && role !== "OTHER" ? ` · ${role.replace(/_/g, " ").toLowerCase()}` : ""}</span>
      <span className="opacity-75">Sent as <span className="font-mono">{label}</span></span>
    </span>
  )
}

/** A reply after rehydration on this device: restored values tinted by type, restored passages collapsible. */
export function RestoredText({ segments = [] }: { segments?: Segment[] }) {
  return (
    <>
      {segments.map((s, i) => {
        if (!s.label) return <span key={i}>{s.text}</span>
        if (s.kind === "context") {
          const v = toneVars("context")
          return (
            <Collapsible key={i} className="inline">
              <CollapsibleTrigger className="group inline-flex cursor-pointer items-center gap-0.5 align-baseline">
                <ChevronRight className="size-3 text-muted-foreground transition-transform group-data-[panel-open]:rotate-90" aria-hidden />
                <Chip label={s.label} context tip="Restored from your vault. Click to read it." />
              </CollapsibleTrigger>
              <CollapsibleContent className="my-2 block border-l-2 px-3 py-2 text-[14.5px]" style={{ background: v.bg, borderColor: v.line }}>
                {s.text}
              </CollapsibleContent>
            </Collapsible>
          )
        }
        if (s.kind === "unknown") {
          return <Chip key={i} label={s.label} tip="Not in your vault: the model made this placeholder up." />
        }
        const v = toneVars(toneForLabel(s.label, "entity"))
        return (
          <Tip key={i} tip={<>Restored on this device from <span className="font-mono">{s.label}</span></>}>
            <mark className="rounded-[3px] px-0.5 text-inherit underline decoration-dotted decoration-[1.5px] underline-offset-[3px]"
              style={{ background: v.bg, textDecorationColor: v.line }}>
              {s.text}
            </mark>
          </Tip>
        )
      })}
    </>
  )
}
