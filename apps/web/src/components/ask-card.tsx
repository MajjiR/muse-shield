import { MaskedText } from "@/components/privacy-text"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { Ask, Level } from "@muse-shield/core"
import { Eye, Loader2, ShieldQuestion } from "lucide-react"
import { motion } from "motion/react"
import { useState } from "react"

const LEVELS: Record<Level, { label: string; risk: string; help: string; tone: string }> = {
  shape: { label: "Shape", risk: "Low exposure", help: "Structure only. Names and numbers inside stay masked.", tone: "text-masked-ink" },
  summary: { label: "Summary", risk: "Low exposure", help: "A one-line gist with no names or numbers.", tone: "text-masked-ink" },
  full: { label: "Full text", risk: "High exposure", help: "The real text, including every value inside it.", tone: "text-destructive" },
}

export function AskCard({ ask, busy, onDecide }: { ask: Ask; busy: boolean; onDecide: (decision: "allow" | "deny", level: Level) => void }) {
  const levels = (["shape", "summary", "full"] as Level[]).filter((l) => ask.previews?.[l] != null)
  const [level, setLevel] = useState<Level>(ask.level)
  const preview = ask.previews?.[level] ?? ask.preview
  const meta = LEVELS[level]

  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 380, damping: 30 }}
      className="w-full overflow-hidden rounded-2xl border border-context-line/40 bg-card shadow-float"
      role="dialog"
      aria-label="Muse Spark is asking to see hidden content"
    >
      <div className="flex items-start gap-3 border-b bg-context/40 px-5 py-4">
        <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-context text-context-ink ring-1 ring-context-line/30">
          <ShieldQuestion className="size-4" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="text-[15px] font-semibold tracking-tight">
            Muse Spark is asking to see {ask.kind === "context" ? "a hidden passage" : "a hidden value"}
          </p>
          <p className="mt-0.5 text-[13px] text-muted-foreground">
            <span className="font-mono text-xs text-context-ink">{ask.label}</span>
            {" · "}“{ask.reason || "It says it needs this to answer."}”
          </p>
        </div>
      </div>

      <div className="space-y-4 px-5 py-4">
        {levels.length > 1 && (
          <div>
            <div className="mb-2 text-xs font-medium text-muted-foreground">How much do you want to share?</div>
            <div className="inline-flex rounded-lg bg-muted p-1" role="radiogroup" aria-label="Reveal level">
              {levels.map((l) => (
                <button
                  key={l}
                  type="button"
                  role="radio"
                  aria-checked={l === level}
                  onClick={() => setLevel(l)}
                  className={cn(
                    "relative rounded-md px-3.5 py-1.5 text-[13px] font-medium transition-colors",
                    l === level ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {l === level && (
                    <motion.span layoutId={`lvl-${ask.ask_id}`} className="absolute inset-0 rounded-md bg-card shadow-soft"
                      transition={{ type: "spring", stiffness: 500, damping: 38 }} />
                  )}
                  <span className="relative">{LEVELS[l].label}</span>
                </button>
              ))}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              <span className={cn("font-medium", meta.tone)}>{meta.risk}.</span> {meta.help}
            </p>
          </div>
        )}

        <div>
          <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Eye className="size-3.5" aria-hidden /> Exactly this will be sent if you allow it
          </div>
          <motion.div
            key={level}
            initial={{ opacity: 0.4 }}
            animate={{ opacity: 1 }}
            className={cn(
              "rounded-xl border bg-subtle px-3.5 py-3 text-[13px] leading-relaxed whitespace-pre-wrap",
              level === "full" && "border-destructive/40 bg-destructive/5",
            )}
          >
            <MaskedText text={preview} />
          </motion.div>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 border-t bg-subtle px-5 py-3">
        <span className="text-xs text-muted-foreground">Your choice is logged in this chat’s consent history.</span>
        <div className="flex gap-2">
          <Button variant="ghost" disabled={busy} onClick={() => onDecide("deny", level)}>Don’t share</Button>
          <Button disabled={busy} onClick={() => onDecide("allow", level)} className={cn(level === "full" && "bg-destructive hover:bg-destructive/90")}>
            {busy && <Loader2 className="animate-spin" />} Share {meta.label.toLowerCase()}
          </Button>
        </div>
      </div>
    </motion.div>
  )
}
