import { MaskedText } from "@/components/privacy-text"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { Ask, Level } from "@muse-shield/core"
import { ShieldAlert } from "lucide-react"
import { useState } from "react"

const LEVEL_HELP: Record<Level, string> = {
  shape: "structure only: inner names and numbers stay masked",
  summary: "a one-line gist with no names or numbers",
  full: "the real text, including the values inside it",
}

export function AskCard({ ask, busy, onDecide }: { ask: Ask; busy: boolean; onDecide: (decision: "allow" | "deny", level: Level) => void }) {
  const levels = (Object.keys(ask.previews ?? {}) as Level[]).filter((l) => ask.previews[l] != null)
  const [level, setLevel] = useState<Level>(ask.level)
  const preview = ask.previews?.[level] ?? ask.preview
  const isContext = ask.kind === "context"

  return (
    <div className="w-full max-w-3xl rounded-2xl border border-context-line bg-card p-4">
      <div className="mb-1 flex items-center gap-2 text-sm font-semibold">
        <ShieldAlert className="size-4 text-context-line" aria-hidden />
        Muse Spark wants to see {isContext ? "a hidden passage" : "a hidden value"}
        <span className="rounded-[5px] border border-context-line bg-context px-1 font-mono text-[11.5px]">{ask.label}</span>
      </div>
      <p className="mb-3 text-sm text-muted-foreground">{ask.reason || "It says it needs this to answer."}</p>

      {levels.length > 1 && (
        <div className="mb-2 flex flex-wrap gap-1.5" role="group" aria-label="How much to reveal">
          {levels.map((l) => (
            <button
              key={l}
              type="button"
              aria-pressed={l === level}
              onClick={() => setLevel(l)}
              className={cn(
                "rounded-full border px-3 py-0.5 text-xs",
                l === level ? "border-primary font-semibold text-primary" : "border-border bg-muted",
              )}
            >
              {l}
            </button>
          ))}
          <span className="self-center text-xs text-muted-foreground">{LEVEL_HELP[level]}</span>
        </div>
      )}

      <div className="mb-1 text-xs text-muted-foreground">Exactly this will be sent if you allow it:</div>
      <div
        className={cn(
          "mb-3 rounded-lg bg-muted px-3 py-2 font-mono text-xs whitespace-pre-wrap",
          level === "full" && "border border-destructive",
        )}
      >
        <MaskedText text={preview} />
      </div>
      {level === "full" && (
        <p className="mb-3 text-xs text-destructive">This sends real values to Muse Spark.</p>
      )}
      <div className="flex gap-2">
        <Button disabled={busy} onClick={() => onDecide("allow", level)}>Allow {level}</Button>
        <Button disabled={busy} variant="destructive" onClick={() => onDecide("deny", level)}>Deny</Button>
      </div>
    </div>
  )
}
