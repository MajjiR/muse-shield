import { MaskedText, OriginalText, RestoredText } from "@/components/privacy-text"
import { cn } from "@/lib/utils"
import type { Message } from "@muse-shield/core"
import { useState } from "react"

export function MessageView({ m, kinds }: { m: Message; kinds: Record<string, string> }) {
  const [saw, setSaw] = useState(false)

  if (m.role === "reveal") {
    const { decision, label, level } = m.meta
    return (
      <div className="self-center rounded-full bg-muted px-3 py-0.5 text-xs text-muted-foreground">
        {decision === "allow" ? `You allowed Muse Spark to see ${label} (${level})` : `You declined to reveal ${label}`}
      </div>
    )
  }

  const user = m.role === "user"
  const cost = m.meta.cost_usd ? `${user ? "masking" : "answer"} $${m.meta.cost_usd.toFixed(4)}` : null
  return (
    <div className={cn("flex w-fit max-w-3xl flex-col", user ? "self-end items-end" : "self-start")}>
      <div
        className={cn(
          "rounded-2xl px-3.5 py-2.5 whitespace-pre-wrap break-words",
          user ? "rounded-br-sm bg-primary/10" : "rounded-bl-sm border bg-card",
        )}
      >
        {user ? <OriginalText text={m.text} spans={m.meta.spans} /> : <RestoredText segments={m.segments} />}
      </div>
      <div className="mt-1 flex gap-3 px-1 text-[11.5px] text-muted-foreground">
        {cost && <span>{cost}</span>}
        <button type="button" className="text-primary hover:underline" onClick={() => setSaw((s) => !s)}>
          {saw ? "Hide what Muse Spark saw" : "What Muse Spark saw"}
        </button>
      </div>
      {saw && (
        <div className="mt-1.5 rounded-xl border border-dashed bg-muted px-3 py-2 font-mono text-xs whitespace-pre-wrap">
          <MaskedText text={m.masked_text} kinds={kinds} />
        </div>
      )}
    </div>
  )
}
