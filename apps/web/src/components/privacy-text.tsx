import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { toneForLabel, toneForType, toneVars } from "@/lib/tones"
import { looksLikeContext, splitLabels, type Segment, type Span } from "@muse-shield/core"
import { ChevronRight } from "lucide-react"
import type { Element as HastElement, Root as HastRoot, RootContent as HastNode } from "hast"
import type { CSSProperties, ReactNode } from "react"
import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"

type HastParent = HastRoot | HastElement

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
export function OriginalText({ text, spans: raw = [], animate, stagger = 110 }: { text: string; spans?: Span[]; animate?: boolean; stagger?: number }) {
  const spans = toUtf16(text, raw)
  const ents = spans.filter((s) => s.kind !== "context").sort((a, b) => a.start - b.start)
  const ctxs = spans.filter((s) => s.kind === "context").sort((a, b) => a.start - b.start)
  let order = 0
  const reveal = (line: string): { className: string; style: CSSProperties } =>
    animate
      ? { className: "ms-mark-in", style: { ["--ms-delay" as string]: `${order++ * stagger}ms`, ["--ms-glow" as string]: `color-mix(in srgb, ${line} 45%, transparent)` } }
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

/** The engine counts offsets in Unicode code points; JavaScript strings index UTF-16 units. They differ after
 * characters outside the Basic Multilingual Plane (emoji, math letters common in PDFs), so convert. */
function toUtf16(text: string, spans: Span[]): Span[] {
  if (!/[\uD800-\uDBFF]/.test(text)) return spans
  const at: number[] = []
  let u = 0
  for (const ch of text) {
    at.push(u)
    u += ch.length
  }
  at.push(u)
  return spans.map((s) => ({ ...s, start: at[s.start] ?? s.start, end: at[s.end] ?? s.end }))
}

function TipBody({ kind, role, label }: { kind: string; role?: string | null; label: string }) {
  return (
    <span className="flex flex-col gap-0.5">
      <span className="font-medium">{kind.replace(/_/g, " ").toLowerCase()}{role && role !== "OTHER" ? ` · ${role.replace(/_/g, " ").toLowerCase()}` : ""}</span>
      <span className="opacity-75">Sent as <span className="font-mono">{label}</span></span>
    </span>
  )
}

/** One restored segment: a value tinted by type, a collapsible passage, or a placeholder the vault doesn't know. */
function RestoredSegment({ s }: { s: Segment }) {
  if (!s.label) return <>{s.text}</>
  if (s.kind === "context") {
    const v = toneVars("context")
    // Replies carry a passage as its summary (text) with the real passage in full; older replies only have text.
    const full = s.full ?? s.text
    const summary = s.full != null ? s.text : null
    return (
      <Collapsible className="inline">
        {summary && (
          <Tip tip={<>Summary of the hidden passage <span className="font-mono">{s.label}</span>. Expand to read the real text.</>}>
            <mark className="rounded-[3px] px-1 py-0.5 text-inherit box-decoration-clone" style={{ background: v.bg, boxShadow: `inset 2px 0 0 ${v.line}` }}>
              {summary}
            </mark>
          </Tip>
        )}
        <CollapsibleTrigger aria-label={`Show the full passage ${s.label}`}
          className={cn("group inline-flex cursor-pointer items-center gap-0.5 align-baseline", summary && "ml-1")}>
          <ChevronRight className="size-3 text-muted-foreground transition-transform group-data-[panel-open]:rotate-90" aria-hidden />
          <Chip label={s.label} context size={summary ? "xs" : "sm"} tip="Restored from your vault. Click to read the full passage." />
        </CollapsibleTrigger>
        <CollapsibleContent className="my-2 block border-l-2 px-3 py-2 text-[14.5px] whitespace-pre-wrap" style={{ background: v.bg, borderColor: v.line }}>
          {full}
        </CollapsibleContent>
      </Collapsible>
    )
  }
  if (s.kind === "unknown") return <Chip label={s.label} tip="Not in your vault: the model made this placeholder up." />
  const v = toneVars(toneForLabel(s.label, "entity"))
  return (
    <Tip tip={<>Restored on this device from <span className="font-mono">{s.label}</span></>}>
      <mark className="rounded-[3px] px-0.5 text-inherit underline decoration-dotted decoration-[1.5px] underline-offset-[3px]"
        style={{ background: v.bg, textDecorationColor: v.line }}>
        {s.text}
      </mark>
    </Tip>
  )
}

// Restored values stand in the markdown source as private-use sentinels, so a value's own text can never
// be read as markdown; after parsing, each sentinel becomes a span the renderer swaps for its segment.
const SENTINEL = /\uE000(\d+)\uE001/g

function rehypeSegments() {
  const split = (node: HastParent) => {
    node.children = node.children.flatMap((child): HastNode[] => {
      if (child.type !== "text") {
        if ("children" in child) split(child)
        return [child]
      }
      const parts: HastNode[] = []
      let last = 0
      for (const m of child.value.matchAll(SENTINEL)) {
        if (m.index > last) parts.push({ type: "text", value: child.value.slice(last, m.index) })
        parts.push({ type: "element", tagName: "span", properties: { dataSeg: m[1] }, children: [] })
        last = m.index + m[0].length
      }
      if (!parts.length) return [child]
      if (last < child.value.length) parts.push({ type: "text", value: child.value.slice(last) })
      return parts
    })
  }
  return (tree: HastRoot) => split(tree)
}

const md: Components = {
  p: ({ children }) => <div className="my-3 first:mt-0 last:mb-0">{children}</div>,
  h1: ({ children }) => <h3 className="mt-6 mb-2 font-heading text-[24px] leading-tight font-normal tracking-[-0.02em] first:mt-0">{children}</h3>,
  h2: ({ children }) => <h3 className="mt-6 mb-2 font-heading text-[22px] leading-tight font-normal tracking-[-0.02em] first:mt-0">{children}</h3>,
  h3: ({ children }) => <h4 className="mt-4 mb-1.5 text-[16px] font-semibold first:mt-0">{children}</h4>,
  h4: ({ children }) => <h4 className="mt-4 mb-1.5 font-semibold first:mt-0">{children}</h4>,
  ul: ({ children }) => <ul className="my-3 list-disc space-y-1 pl-6 marker:text-muted-foreground">{children}</ul>,
  ol: ({ children }) => <ol className="my-3 list-decimal space-y-1 pl-6 marker:text-muted-foreground">{children}</ol>,
  li: ({ children }) => <li className="pl-1">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer noopener" className="underline underline-offset-2">{children}</a>,
  blockquote: ({ children }) => <blockquote className="my-3 border-l-2 pl-4 text-muted-foreground">{children}</blockquote>,
  hr: () => <hr className="my-5 border-border" />,
  pre: ({ children }) => <pre className="my-3 overflow-x-auto rounded-md bg-muted px-4 py-3 font-mono text-[13px] leading-relaxed">{children}</pre>,
  code: ({ children, className }) => <code className={cn(className, "font-mono text-[0.88em] [:not(pre)>&]:rounded-[3px] [:not(pre)>&]:bg-muted [:not(pre)>&]:px-1 [:not(pre)>&]:py-px")}>{children}</code>,
  table: ({ children }) => <div className="my-3 overflow-x-auto"><table className="w-full border-collapse text-[14px]">{children}</table></div>,
  th: ({ children }) => <th className="border-b px-3 py-1.5 text-left font-semibold">{children}</th>,
  td: ({ children }) => <td className="border-b px-3 py-1.5 align-top">{children}</td>,
}

/** A reply after rehydration on this device, rendered as markdown, with restored values tinted by type. */
export function RestoredText({ segments = [] }: { segments?: Segment[] }) {
  const source = segments.map((s, i) => (s.label ? `\uE000${i}\uE001` : s.text.replace(/[\uE000\uE001]/g, ""))).join("")
  const components: Components = {
    ...md,
    span: ({ node, children, ...props }) => {
      const i = node?.properties?.dataSeg
      return i != null ? <RestoredSegment s={segments[Number(i)]} /> : <span {...props}>{children}</span>
    },
  }
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSegments]} components={components}>
      {source}
    </ReactMarkdown>
  )
}
