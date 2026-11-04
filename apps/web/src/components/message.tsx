import { CategoryLine } from "@/components/categories"
import { MaskedText, OriginalText, RestoredText } from "@/components/privacy-text"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import type { Message } from "@muse-shield/core"
import { Check, Copy, EyeOff, ScanEye, ShieldCheck, ShieldX, Sparkles } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { useState } from "react"

const enter = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.22, ease: [0.2, 0.8, 0.2, 1] } } as const

export function MessageView({ m, kinds }: { m: Message; kinds: Record<string, string> }) {
  const [saw, setSaw] = useState(false)
  const [copied, setCopied] = useState(false)

  if (m.role === "reveal") {
    const { decision, label, level } = m.meta
    const allowed = decision === "allow"
    return (
      <motion.div {...enter} className="flex items-center justify-center gap-2 py-1 text-xs text-muted-foreground">
        <span className="h-px w-10 bg-border" />
        {allowed ? <ShieldCheck className="size-3.5 text-foreground" aria-hidden /> : <ShieldX className="size-3.5" aria-hidden />}
        <span>
          {allowed ? "You shared" : "You declined to share"} <span className="font-mono text-[11px]">{label}</span>
          {allowed && <> · {level}</>}
        </span>
        <span className="h-px w-10 bg-border" />
      </motion.div>
    )
  }

  const user = m.role === "user"
  const masked = (m.meta.spans ?? []).length
  const cost = m.meta.cost_usd ? `$${m.meta.cost_usd.toFixed(4)}` : null
  const copy = async () => {
    await navigator.clipboard.writeText(m.text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1200)
  }

  const actions = (
    <div className={cn("flex items-center gap-1 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100",
      saw && "opacity-100", user && "flex-row-reverse")}>
      <IconAction label={saw ? "Hide what Muse Spark saw" : "See what Muse Spark saw"} onClick={() => setSaw((s) => !s)} active={saw}>
        {saw ? <EyeOff /> : <ScanEye />}
      </IconAction>
      <IconAction label={copied ? "Copied" : "Copy"} onClick={copy}>{copied ? <Check /> : <Copy />}</IconAction>
      <span className="tabular px-1 text-[11px]">
        {user && masked > 0 && `${masked} masked · `}{cost && `${user ? "masking" : "answer"} ${cost}`}
      </span>
    </div>
  )

  return (
    <motion.div {...enter} className={cn("group flex w-full gap-3", user ? "justify-end" : "justify-start")}>
      {!user && (
        <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-sm bg-foreground text-background">
          <Sparkles className="size-3.5" aria-hidden />
        </span>
      )}
      <div className={cn("flex min-w-0 max-w-[min(42rem,85%)] flex-col gap-1.5", user && "items-end")}>
        {!user && <span className="text-[13px] font-semibold">Muse Spark</span>}
        <div className={cn("text-[16px] leading-[1.7] break-words",
          user ? "rounded-md bg-muted px-4 py-2.5 whitespace-pre-wrap" : "pt-0.5")}>
          {user ? <OriginalText text={m.text} spans={m.meta.spans} /> : <RestoredText segments={m.segments} />}
        </div>
        {user && !!m.meta.categories?.length && <CategoryLine categories={m.meta.categories} className="justify-end" />}
        <AnimatePresence initial={false}>
          {saw && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="w-full overflow-hidden"
            >
              <div className="rounded-md border border-dashed bg-subtle px-3.5 py-2.5 text-[13px] leading-relaxed whitespace-pre-wrap">
                <div className="mb-1 eyebrow text-muted-foreground">
                  {user ? "Sent to Muse Spark" : "Muse Spark wrote"}
                </div>
                <MaskedText text={m.masked_text} kinds={kinds} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        {actions}
      </div>
    </motion.div>
  )
}

function IconAction({ label, onClick, active, children }: { label: string; onClick: () => void; active?: boolean; children: React.ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button type="button" aria-label={label} onClick={onClick}
            className={cn("grid size-7 place-items-center rounded-md hover:bg-muted hover:text-foreground [&_svg]:size-3.5", active && "bg-muted text-foreground")} />
        }
      >
        {children}
      </TooltipTrigger>
      <TooltipContent className="text-xs">{label}</TooltipContent>
    </Tooltip>
  )
}
