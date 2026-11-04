import { MaskedText, OriginalText } from "@/components/privacy-text"
import { Button } from "@/components/ui/button"
import { engine } from "@/lib/engine"
import { toneForType, toneVars } from "@/lib/tones"
import { cn } from "@/lib/utils"
import type { DocumentDetail, DocumentInfo, DocumentWarning, Span } from "@muse-shield/core"
import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, Download, Eye, FileText, Presentation, ShieldAlert, ShieldCheck, X } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"

const TERMINAL = new Set(["ready", "blocked", "failed"])
const FORMAT_LABEL = { pdf: "PDF", docx: "Word", pptx: "PowerPoint" } as const

const WARNING_TEXT: Record<string, (w: DocumentWarning) => string> = {
  images_removed: (w) => `${w.count} image${w.count === 1 ? "" : "s"} removed (not checked)`,
  charts_removed: (w) => `${w.count} chart${w.count === 1 ? "" : "s"} or embedded object${w.count === 1 ? "" : "s"} removed`,
  embedded_removed: (w) => `${w.count} embedded object${w.count === 1 ? "" : "s"} removed`,
  comments_removed: (w) => `${w.count} comment${w.count === 1 ? "" : "s"} removed`,
  tracked_changes_accepted: () => "Tracked changes accepted (deleted text is gone)",
  links_removed: (w) => `${w.count} link${w.count === 1 ? "" : "s"} removed`,
  fields_unlinked: () => "Fields turned into plain text",
  hidden_slides: (w) => `Hidden slides masked too${w.where ? ` (${w.where.join(", ")})` : ""}`,
  annotations_removed: (w) => `${w.count} annotation${w.count === 1 ? "" : "s"} removed`,
  form_fields_removed: (w) => `${w.count} form field${w.count === 1 ? "" : "s"} removed (values not checked)`,
  bookmarks_removed: () => "Bookmarks removed",
  attachments_removed: (w) => `${w.count} attachment${w.count === 1 ? "" : "s"} removed`,
  offpage_text_removed: () => "Text outside the page removed",
  layers_shown: () => "Hidden layers were included",
  guard_conflict: () => "A short value also appears inside other words; the chat may refuse to send it",
  collateral: (w) => `${w.count} nearby word${w.count === 1 ? "" : "s"} lost under a box`,
  labels_unreadable: (w) => `${w.count} label${w.count === 1 ? "" : "s"} too small to read`,
  repaired: () => "The PDF was damaged and has been repaired",
}

function statusLine(d: DocumentInfo): string {
  switch (d.status) {
    case "extracting": return "Reading the file…"
    case "analysing": return d.progress?.total ? `Analysing ${d.progress.done} of ${d.progress.total} sections…` : "Analysing for sensitive details…"
    case "verifying": return "Checking the masked copy…"
    case "ready": return `Checked ${d.verify?.checks.toLocaleString() ?? 0} places: no masked value left`
    case "blocked": return "Masked copy blocked: a value was still in the file"
    case "failed": return d.error ?? "Couldn't mask this file"
  }
}

/** Counts by type, e.g. {PERSON: 3, CONTEXT_DEAL: 1}, as pastel chips. */
function TypeCounts({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts).filter(([k]) => k !== "verified")
  if (!entries.length) return <span className="text-[12px] text-muted-foreground">Nothing sensitive found</span>
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([type, n], i) => {
        const ctx = type.startsWith("CONTEXT_")
        const v = toneVars(ctx ? "context" : toneForType(type))
        const name = (ctx ? "passage" : type.replace(/_/g, " ")).toLowerCase()
        return (
          <motion.span key={type} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.06 }}
            className="tabular rounded-[3px] border px-1.5 py-px text-[11.5px]" style={{ background: v.bg, borderColor: v.line, color: v.ink }}>
            {n} {name}{n === 1 || name.endsWith("s") ? "" : "s"}
          </motion.span>
        )
      })}
    </div>
  )
}

/** A document in the thread or the composer. Polls the engine until masking finishes. */
export function DocumentCard({ doc, onRemove, onStatus, align = "end" }: {
  doc: DocumentInfo; onRemove?: () => void; onStatus?: (d: DocumentInfo) => void; align?: "start" | "end"
}) {
  const q = useQuery({
    queryKey: ["document", doc.doc_id],
    queryFn: () => engine.document(doc.doc_id),
    initialData: doc,
    refetchInterval: (query) => (TERMINAL.has(query.state.data?.status ?? "") ? false : 700),
  })
  const d = q.data ?? doc
  const [previewing, setPreviewing] = useState(false)
  useEffect(() => { onStatus?.(d) }, [d.status, d.doc_id]) // eslint-disable-line react-hooks/exhaustive-deps
  const busy = !TERMINAL.has(d.status)
  const Icon = d.format === "pptx" ? Presentation : FileText
  const unchecked = d.page_status.filter((p) => p.status !== "ok" && p.status !== "empty")
  const unit = d.format === "pptx" ? "slide" : "page"

  const download = async () => {
    try {
      const { blob, name } = await engine.downloadMasked(d.doc_id)
      const url = URL.createObjectURL(blob)
      const a = Object.assign(document.createElement("a"), { href: url, download: name })
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      className={cn("flex w-full", align === "end" ? "justify-end" : "justify-start")}>
      <div className="w-full max-w-[min(30rem,92%)] overflow-hidden rounded-md border bg-card">
        <div className="flex items-start gap-3 px-3.5 py-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-sm border bg-muted text-foreground">
            <Icon className="size-4.5" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <div className={cn("truncate text-[14px] font-medium", busy && "ms-analysing")} title={d.filename}>{d.filename}</div>
            <div className="tabular text-[12px] text-muted-foreground">
              {FORMAT_LABEL[d.format]}
              {d.pages ? ` · ${d.pages} ${unit}${d.pages === 1 ? "" : "s"}` : ""} · {(d.bytes / 1024).toFixed(0)} KB
              {d.n ? ` · Document ${d.n}` : ""}
            </div>
          </div>
          {onRemove && (
            <button type="button" aria-label="Remove document" onClick={onRemove}
              className="grid size-6 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground">
              <X className="size-3.5" />
            </button>
          )}
        </div>

        {busy && (
          <div className="h-0.5 overflow-hidden bg-border" aria-hidden>
            {d.progress?.total ? (
              <motion.div className="h-full bg-foreground/60" animate={{ width: `${(100 * d.progress.done) / d.progress.total}%` }} />
            ) : (
              <span className="block h-full w-1/3 bg-foreground/50" style={{ animation: "ms-progress 1.2s ease-in-out infinite" }} />
            )}
          </div>
        )}

        <div className="space-y-2 border-t px-3.5 py-2.5">
          <div className={cn("flex items-center gap-1.5 text-[12.5px]", d.status === "blocked" || d.status === "failed" ? "text-foreground" : "text-muted-foreground")}
            aria-live="polite">
            {d.status === "ready" ? <ShieldCheck className="size-3.5 text-foreground" aria-hidden />
              : d.status === "blocked" || d.status === "failed" ? <ShieldAlert className="size-3.5" aria-hidden /> : null}
            <span>{statusLine(d)}</span>
          </div>
          {d.status === "blocked" && d.verify && (
            <ul className="space-y-0.5 text-[12px] text-muted-foreground">
              {d.verify.failures.slice(0, 4).map((f, i) => (
                <li key={i}><span className="font-mono text-[11px] text-foreground">{f.label}</span> still in {f.where}</li>
              ))}
            </ul>
          )}
          {(d.status === "ready" || d.status === "blocked") && <TypeCounts counts={d.counts} />}
          {unchecked.length > 0 && (
            <p className="flex items-start gap-1.5 text-[12px]">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              <span>
                {unit[0].toUpperCase() + unit.slice(1)}{unchecked.length > 1 ? "s" : ""} {unchecked.map((p) => p.page).join(", ")} not
                checked (no readable text, e.g. a scan): removed from the copy and not sent.
              </span>
            </p>
          )}
          {d.warnings.length > 0 && (d.status === "ready" || d.status === "blocked") && (
            <ul className="space-y-0.5 text-[12px] text-muted-foreground">
              {d.warnings.map((w) => <li key={w.code}>· {(WARNING_TEXT[w.code] ?? (() => w.code.replace(/_/g, " ")))(w)}</li>)}
            </ul>
          )}
        </div>

        {(d.status === "ready" || d.status === "blocked") && (
          <div className="flex items-center justify-end gap-1.5 border-t bg-subtle px-2.5 py-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setPreviewing(true)}><Eye /> Preview</Button>
            <Button type="button" size="sm" disabled={!d.has_masked_copy} onClick={download}><Download /> Masked copy</Button>
          </div>
        )}
      </div>
      <AnimatePresence>{previewing && <DocumentPreview docId={d.doc_id} onClose={() => setPreviewing(false)} />}</AnimatePresence>
    </motion.div>
  )
}

/** The masked version of original[start:end], from the spans inside it. */
function maskedSlice(text: string, spans: Span[], start: number, end: number) {
  const reps = spans.filter((s) => s.start >= start && s.end <= end && (s.kind === "context" || !s.in_context)).sort((a, b) => a.start - b.start)
  let out = "", cur = start
  for (const s of reps) {
    if (s.start < cur) continue
    out += text.slice(cur, s.start) + s.placeholder
    cur = s.end
  }
  return out + text.slice(cur, end)
}

/** Side by side, section by section: what the file says (on this device) and what Muse Spark gets. */
function DocumentPreview({ docId, onClose }: { docId: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ["document-detail", docId], queryFn: () => engine.documentDetail(docId) })
  const [i, setI] = useState(0)
  const d: DocumentDetail | undefined = q.data
  const units = useMemo(() => d?.units ?? [], [d])
  const unit = units[i]
  const local = useMemo(() => {
    if (!d || !unit) return null
    const [s, e] = unit
    const inside = d.spans.filter((x) => x.start >= s && x.end <= e).map((x) => ({ ...x, start: x.start - s, end: x.end - s }))
    return { text: d.text.slice(s, e), spans: inside, masked: maskedSlice(d.text, d.spans, s, e) }
  }, [d, unit])
  const kinds = useMemo(() => Object.fromEntries((d?.spans ?? []).map((s) => [s.placeholder, s.kind])), [d])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  return (
    <motion.div className="fixed inset-0 z-50 grid place-items-center bg-foreground/20 p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      exit={{ opacity: 0 }} onClick={onClose} role="dialog" aria-modal aria-label="Document preview">
      <motion.div initial={{ y: 12, scale: 0.98 }} animate={{ y: 0, scale: 1 }} exit={{ y: 8, opacity: 0 }}
        onClick={(e) => e.stopPropagation()} className="flex max-h-[85vh] w-full max-w-5xl flex-col overflow-hidden rounded-md border bg-card shadow-soft">
        <div className="flex items-center gap-3 border-b px-4 py-3">
          <ShieldCheck className="size-4" aria-hidden />
          <strong className="truncate text-[14px] font-semibold">{d?.filename ?? "Document"}</strong>
          <span className="ml-auto text-[12px] text-muted-foreground tabular">{units.length ? `Section ${i + 1} of ${units.length}` : ""}</span>
          <button type="button" aria-label="Close preview" onClick={onClose} className="grid size-7 place-items-center rounded-md text-muted-foreground hover:bg-muted">
            <X className="size-4" />
          </button>
        </div>
        {units.length > 1 && (
          <div className="flex gap-1 overflow-x-auto border-b px-3 py-2">
            {units.map((u, k) => (
              <button key={k} type="button" onClick={() => setI(k)}
                className={cn("shrink-0 rounded-sm px-2 py-1 text-[12px]", k === i ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted")}>
                {u[2] || `Section ${k + 1}`}
              </button>
            ))}
          </div>
        )}
        <div className="grid min-h-0 flex-1 grid-cols-2 overflow-y-auto max-md:grid-cols-1">
          <div className="border-r px-4 py-3 max-md:border-r-0 max-md:border-b">
            <div className="mb-1.5 eyebrow text-muted-foreground">In your file</div>
            <div className="text-[13.5px] leading-relaxed whitespace-pre-wrap break-words">
              {local ? <OriginalText key={i} text={local.text} spans={local.spans} animate stagger={Math.min(110, 2500 / Math.max(1, local.spans.length))} />
                : <span className="ms-analysing">Loading…</span>}
            </div>
          </div>
          <div className="bg-subtle px-4 py-3">
            <div className="mb-1.5 eyebrow text-muted-foreground">Muse Spark receives</div>
            <div className="text-[13.5px] leading-relaxed whitespace-pre-wrap break-words">{local && <MaskedText text={local.masked} kinds={kinds} />}</div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  )
}
