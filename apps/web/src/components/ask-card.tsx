import { MaskedText } from "@/components/privacy-text"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { Ask, AskChoice, AskItem, Level } from "@muse-shield/core"
import { Check, Eye, Loader2, ShieldQuestion } from "lucide-react"
import { motion } from "motion/react"
import { useState } from "react"

const LEVELS: Record<Level, { label: string; risk: string; help: string; tone: string }> = {
  shape: { label: "Shape", risk: "Low exposure", help: "Structure only. Names and numbers inside stay masked.", tone: "text-foreground" },
  summary: { label: "Summary", risk: "Low exposure", help: "A one-line gist with no names or numbers.", tone: "text-foreground" },
  full: { label: "Full text", risk: "High exposure", help: "The real text, including every value inside it.", tone: "text-foreground underline decoration-2 underline-offset-2" },
}

type Decide = (decision: "allow" | "deny", level: Level, items?: Record<string, AskChoice>) => void

export function AskCard({ ask, busy, onDecide }: { ask: Ask; busy: boolean; onDecide: Decide }) {
  if ((ask.items?.length ?? 0) > 1) return <MultiAskCard ask={ask} busy={busy} onDecide={onDecide} />
  return <SingleAskCard ask={ask} busy={busy} onDecide={onDecide} />
}

function SingleAskCard({ ask, busy, onDecide }: { ask: Ask; busy: boolean; onDecide: Decide }) {
  const levels = (["shape", "summary", "full"] as Level[]).filter((l) => ask.previews?.[l] != null)
  // Start at the least exposure on offer, whatever Spark asked for; the user can step up.
  const [level, setLevel] = useState<Level>(levels[0] ?? ask.level)
  const preview = ask.previews?.[level] ?? ask.preview
  const imageUrl = ask.kind === "image" ? ask.previews?.full : undefined // the original, served by this device's engine
  const meta = LEVELS[level]

  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 380, damping: 30 }}
      className="w-full overflow-hidden rounded-md border border-foreground/20 bg-card shadow-soft"
      role="dialog"
      aria-label="Muse Spark is asking to see hidden content"
    >
      <div className="flex items-start gap-3 border-b px-5 py-4">
        <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-sm bg-foreground text-background">
          <ShieldQuestion className="size-4" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="font-heading text-[20px] leading-tight font-normal tracking-[-0.01em]">
            Muse Spark is asking to see {ask.kind === "context" ? "a hidden passage" : ask.kind === "image" ? "the original picture" : "a hidden value"}
          </p>
          <p className="mt-0.5 text-[13px] text-muted-foreground">
            <span className="font-mono text-xs text-foreground">{ask.label}</span>
            {" · "}asked for {LEVELS[ask.level].label.toLowerCase()}
            {" · "}“{ask.reason || "It says it needs this to answer."}”
          </p>
        </div>
      </div>

      <div className="space-y-4 px-5 py-4">
        {levels.length > 1 && (
          <div>
            <div className="mb-2 text-xs font-medium text-muted-foreground">How much do you want to share?</div>
            <div className="inline-flex rounded-md border p-0.5" role="radiogroup" aria-label="Reveal level">
              {levels.map((l) => (
                <button
                  key={l}
                  type="button"
                  role="radio"
                  aria-checked={l === level}
                  onClick={() => setLevel(l)}
                  className={cn(
                    "relative rounded-sm px-3.5 py-1 text-[13px] font-medium transition-colors",
                    l === level ? "text-background" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {l === level && (
                    <motion.span layoutId={`lvl-${ask.ask_id}`} className="absolute inset-0 rounded-sm bg-foreground"
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
              "rounded-md border bg-subtle px-3.5 py-3 text-[13px] leading-relaxed whitespace-pre-wrap",
              level === "full" && "border-2 border-dashed border-foreground/70 bg-card",
            )}
          >
            {imageUrl ? (
              <img src={imageUrl} alt="The original picture, unmasked" className="max-h-64 w-auto rounded-sm" />
            ) : (
              <MaskedText text={preview} />
            )}
          </motion.div>
          {ask.kind === "image" && (
            <p className="mt-2 text-xs text-muted-foreground">
              If you share it, Muse Spark sees this picture unmasked (faces and covered parts) for this chat.
            </p>
          )}
          {level === "full" && ask.kind === "entity" && (
            <p className="mt-2 text-xs text-muted-foreground">
              If you share it, Muse Spark may also use it in a web search for this chat. Other tools keep placeholders.
            </p>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 border-t bg-subtle px-5 py-3">
        <span className="text-xs text-muted-foreground">Your choice is logged in this chat’s consent history.</span>
        <div className="flex gap-2">
          <Button variant="ghost" disabled={busy} onClick={() => onDecide("deny", level)}>Don’t share</Button>
          <Button disabled={busy} onClick={() => onDecide("allow", level)} >
            {busy && <Loader2 className="animate-spin" />} {ask.kind === "image" ? "Share original picture" : `Share ${meta.label.toLowerCase()}`}
          </Button>
        </div>
      </div>
    </motion.div>
  )
}

const levelsOf = (item: AskItem) => (["shape", "summary", "full"] as Level[]).filter((l) => item.previews?.[l] != null)
const what = (item: AskItem) => (item.kind === "context" ? "passage" : item.kind === "image" ? "picture" : "value")

/** Several values at once: tick what to share, one decision continues the chat. Unticked values stay hidden. */
function MultiAskCard({ ask, busy, onDecide }: { ask: Ask; busy: boolean; onDecide: Decide }) {
  const items = ask.items ?? []
  const [choice, setChoice] = useState<Record<string, AskChoice>>(() =>
    Object.fromEntries(items.map((i) => [i.label, { decision: "allow", level: levelsOf(i)[0] ?? i.level }])))
  const shared = items.filter((i) => choice[i.label]?.decision === "allow")
  const set = (label: string, patch: Partial<AskChoice>) => setChoice((c) => ({ ...c, [label]: { ...c[label], ...patch } }))
  const denyAll = () => onDecide("deny", ask.level, Object.fromEntries(items.map((i) => [i.label, { decision: "deny" as const }])))

  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 380, damping: 30 }}
      className="w-full overflow-hidden rounded-md border border-foreground/20 bg-card shadow-soft"
      role="dialog"
      aria-label={`Muse Spark is asking to see ${items.length} hidden details`}
    >
      <div className="flex items-start gap-3 border-b px-5 py-4">
        <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-sm bg-foreground text-background">
          <ShieldQuestion className="size-4" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="font-heading text-[20px] leading-tight font-normal tracking-[-0.01em]">
            Muse Spark is asking to see {items.length} hidden details
          </p>
          <p className="mt-0.5 text-[13px] text-muted-foreground">Tick what to share. Anything you leave unticked stays hidden.</p>
        </div>
      </div>

      <ul className="divide-y">
        {items.map((item) => {
          const c = choice[item.label]
          const on = c?.decision === "allow"
          const levels = levelsOf(item)
          const level = (c?.level ?? item.level) as Level
          const preview = item.previews?.[level] ?? item.preview
          return (
            <li key={item.label} className={cn("px-5 py-3 transition-opacity", !on && "opacity-60")}>
              <label className="flex cursor-pointer items-start gap-3">
                <input type="checkbox" checked={on} onChange={(e) => set(item.label, { decision: e.target.checked ? "allow" : "deny" })}
                  className="peer sr-only" aria-label={`Share ${item.label}`} />
                <span className={cn("mt-0.5 grid size-4.5 shrink-0 place-items-center rounded-[4px] border peer-focus-visible:ring-2 peer-focus-visible:ring-ring",
                  on ? "border-foreground bg-foreground text-background" : "border-input")}>
                  {on && <Check className="size-3" aria-hidden />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-x-2 text-[13px]">
                    <span className="font-mono text-xs">{item.label}</span>
                    <span className="text-muted-foreground">{what(item)} · “{item.reason || "needed to answer"}”</span>
                  </span>
                  <span className={cn("mt-1.5 block rounded-md border bg-subtle px-3 py-2 text-[13px] leading-relaxed whitespace-pre-wrap",
                    on && level === "full" && "border-dashed border-foreground/60 bg-card")}>
                    {item.kind === "image" && item.previews?.full
                      ? <img src={item.previews.full} alt="The original picture, unmasked" className="max-h-40 w-auto rounded-sm" />
                      : <MaskedText text={preview} />}
                  </span>
                </span>
              </label>
              {item.kind === "context" && levels.length > 1 && on && (
                <div className="mt-2 ml-7.5 inline-flex rounded-md border p-0.5" role="radiogroup" aria-label={`How much of ${item.label} to share`}>
                  {levels.map((l) => (
                    <button key={l} type="button" role="radio" aria-checked={l === level} onClick={() => set(item.label, { level: l })}
                      className={cn("rounded-sm px-2.5 py-0.5 text-[12px] font-medium",
                        l === level ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground")}>
                      {LEVELS[l].label}
                    </button>
                  ))}
                </div>
              )}
            </li>
          )
        })}
      </ul>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t bg-subtle px-5 py-3">
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Eye className="size-3.5" aria-hidden /> Only the ticked values are sent, exactly as shown. Each choice is logged.
        </span>
        <div className="flex gap-2">
          <Button variant="ghost" disabled={busy} onClick={denyAll}>Don’t share any</Button>
          <Button disabled={busy} onClick={() => onDecide(shared.length ? "allow" : "deny", ask.level, choice)}>
            {busy && <Loader2 className="animate-spin" />} {shared.length ? `Share ${shared.length} of ${items.length}` : "Continue without sharing"}
          </Button>
        </div>
      </div>
    </motion.div>
  )
}
