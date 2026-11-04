import { Button, buttonVariants } from "@/components/ui/button"
import { engine } from "@/lib/engine"
import { toneForType, toneVars } from "@/lib/tones"
import { cn } from "@/lib/utils"
import type { ImageInfo } from "@muse-shield/core"
import { Download, Expand, ImageIcon, ShieldAlert, ShieldCheck, X } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { useEffect, useState } from "react"

/** Faces, codes and the like: everything that isn't a text value. */
const VISUAL = new Set(["face", "photo_id", "signature", "qr_code", "barcode", "license_plate"])  // VISUAL_KINDS in images/meta.py
const BLURRED = new Set(["face", "photo_id"])

function KindCounts({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts)
  if (!entries.length) return <span className="text-[12px] text-muted-foreground">Nothing sensitive found</span>
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([k, n], i) => {
        const visual = VISUAL.has(k)
        const v = toneVars(visual ? "context" : toneForType(k))
        const name = k.replace(/_/g, " ").toLowerCase()
        return (
          <motion.span key={k} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.06 }}
            className="tabular rounded-[3px] border px-1.5 py-px text-[11.5px]" style={{ background: v.bg, borderColor: v.line, color: v.ink }}>
            {n} {name}{n === 1 || name.endsWith("s") ? "" : "s"}{visual && (BLURRED.has(k) ? " blurred" : " hidden")}
          </motion.span>
        )
      })}
    </div>
  )
}

/** While Muse Spark and SAM 3.1 work: the picture, blurred beyond recognition, with a sheen. Local only. */
export function PendingImageCard({ filename, previewUrl, align = "start" }: { filename: string; previewUrl: string; align?: "start" | "end" }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={cn("flex w-full", align === "end" ? "justify-end" : "justify-start")}>
      <div className="w-full max-w-[min(30rem,92%)] overflow-hidden rounded-md border bg-card">
        <div className="relative h-40 overflow-hidden bg-muted">
          <img src={previewUrl} alt="" className="size-full scale-110 object-cover blur-xl" aria-hidden />
          <div className="absolute inset-0 grid place-items-center bg-background/30">
            <span className="ms-analysing text-[13px] font-medium">Blurring faces and covering sensitive text…</span>
          </div>
        </div>
        <div className="h-0.5 overflow-hidden bg-border" aria-hidden>
          <span className="block h-full w-1/3 bg-foreground/50" style={{ animation: "ms-progress 1.2s ease-in-out infinite" }} />
        </div>
        <div className="px-3.5 py-2.5 text-[12.5px] text-muted-foreground">
          <span className="font-medium text-foreground">{filename}</span> · Muse Spark finds values and faces, SAM 3.1 outlines faces,
          then the masked copy is checked again
        </div>
      </div>
    </motion.div>
  )
}

export function ImageCard({ image: d, onRemove, align = "end" }: { image: ImageInfo; onRemove?: () => void; align?: "start" | "end" }) {
  const [open, setOpen] = useState(false)
  const src = engine.maskedImageUrl(d.image_id)
  const leaked = d.verify?.leaked?.length ?? 0
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={cn("flex w-full", align === "end" ? "justify-end" : "justify-start")}>
      <div className="w-full max-w-[min(30rem,92%)] overflow-hidden rounded-md border bg-card">
        <button type="button" onClick={() => setOpen(true)} className="group relative block w-full bg-muted" aria-label="View the masked image">
          <motion.img src={src} alt={`Image ${d.n}, masked`} className="max-h-72 w-full object-contain"
            initial={{ filter: "blur(16px)", opacity: 0.6 }} animate={{ filter: "blur(0px)", opacity: 1 }} transition={{ duration: 0.6 }} />
          <span className="absolute top-2 right-2 grid size-7 place-items-center rounded-sm bg-background/80 opacity-0 transition-opacity group-hover:opacity-100">
            <Expand className="size-3.5" aria-hidden />
          </span>
        </button>
        <div className="flex items-start gap-3 border-t px-3.5 py-2.5">
          <ImageIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] font-medium" title={d.filename}>{d.filename}</div>
            <div className="tabular text-[12px] text-muted-foreground">{d.width} × {d.height} · Image {d.n}</div>
          </div>
          {onRemove && (
            <button type="button" aria-label="Remove image" onClick={onRemove}
              className="grid size-6 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground">
              <X className="size-3.5" />
            </button>
          )}
        </div>
        <div className="space-y-2 border-t px-3.5 py-2.5">
          <div className="flex items-center gap-1.5 text-[12.5px]" aria-live="polite">
            {d.verified ? <ShieldCheck className="size-3.5" aria-hidden /> : <ShieldAlert className="size-3.5" aria-hidden />}
            <span className={d.verified ? "text-muted-foreground" : ""}>
              {d.verified ? "Re-scanned: nothing hidden is readable"
                : d.verify?.error ? "Couldn't re-check the masked image: only its text will be sent"
                : `Re-scan could still read ${leaked || "a"} value${leaked === 1 ? "" : "s"}${d.verify?.faces_left ? " or a face" : ""}: only its text will be sent`}
            </span>
          </div>
          <KindCounts counts={d.counts} />
        </div>
        <div className="flex items-center justify-end gap-1.5 border-t bg-subtle px-2.5 py-2">
          <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(true)}><Expand /> View</Button>
          <a href={engine.maskedImageUrl(d.image_id, true)} download className={buttonVariants({ size: "sm" })}><Download /> Masked copy</a>
        </div>
      </div>
      <AnimatePresence>{open && <ImageViewer image={d} src={src} onClose={() => setOpen(false)} />}</AnimatePresence>
    </motion.div>
  )
}

function ImageViewer({ image: d, src, onClose }: { image: ImageInfo; src: string; onClose: () => void }) {
  const [outlines, setOutlines] = useState(true)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])
  return (
    <motion.div className="fixed inset-0 z-50 grid place-items-center bg-foreground/30 p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      exit={{ opacity: 0 }} onClick={onClose} role="dialog" aria-modal aria-label="Masked image">
      <motion.div initial={{ y: 12, scale: 0.98 }} animate={{ y: 0, scale: 1 }} exit={{ y: 8, opacity: 0 }} onClick={(e) => e.stopPropagation()}
        className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-md border bg-card shadow-soft">
        <div className="flex items-center gap-3 border-b px-4 py-3">
          <ShieldCheck className="size-4" aria-hidden />
          <strong className="truncate text-[14px] font-semibold">What Muse Spark sees: Image {d.n}</strong>
          <label className="ml-auto flex items-center gap-1.5 text-[12px] text-muted-foreground">
            <input type="checkbox" checked={outlines} onChange={(e) => setOutlines(e.target.checked)} /> Outline what was hidden
          </label>
          <button type="button" aria-label="Close" onClick={onClose} className="grid size-7 place-items-center rounded-md text-muted-foreground hover:bg-muted">
            <X className="size-4" />
          </button>
        </div>
        <div className="min-h-0 overflow-auto bg-muted p-3">
          <div className="relative mx-auto w-fit">
            <img src={src} alt={`Image ${d.n}, masked`} className="block max-h-[65vh] max-w-full" />
            {outlines && d.regions.map((r, i) => {
              const v = toneVars(r.kind === "text" ? toneForType(r.type) : "context")
              const [x1, y1, x2, y2] = r.box
              return (
                <motion.span key={i} title={`${r.label || r.kind} · ${r.source}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                  transition={{ delay: i * 0.05 }} className="absolute rounded-[2px] border-2"
                  style={{ left: `${(100 * x1) / d.width}%`, top: `${(100 * y1) / d.height}%`, width: `${(100 * (x2 - x1)) / d.width}%`,
                    height: `${(100 * (y2 - y1)) / d.height}%`, borderColor: v.line }} />
              )
            })}
          </div>
        </div>
        {d.masked_text && (
          <div className="max-h-28 overflow-y-auto border-t px-4 py-2.5 text-[12.5px] leading-relaxed whitespace-pre-wrap text-muted-foreground">
            <span className="mr-1 text-[11px] font-medium tracking-wide uppercase">Text Muse Spark gets</span>{d.masked_text}
          </div>
        )}
      </motion.div>
    </motion.div>
  )
}
