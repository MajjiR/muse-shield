import { AskCard } from "@/components/ask-card"
import { MessageView } from "@/components/message"
import { MaskedText, OriginalText } from "@/components/privacy-text"
import { Button } from "@/components/ui/button"
import { engine } from "@/lib/engine"
import { cn } from "@/lib/utils"
import type { Ask, Level, MaskResult, Turn } from "@muse-shield/core"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowUp, Briefcase, FileText, FlaskConical, KeyRound, Lock, PanelRight, ReceiptText, ScanEye, ShieldCheck, Sparkles, X,
} from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"

const EXAMPLES = [
  { icon: Briefcase, title: "Salary & a big purchase", text: "My name is Rohan and I earn 10 lakh rupees. Tomorrow I'm planning to buy a land at 12-4, MVP Colony, Visakhapatnam. Is that a sensible plan on my salary?" },
  { icon: FileText, title: "Confidential deal", text: "Confidential: Acme Corp has agreed to acquire Kestrel Labs for ₹120 crore. Priya Shah (priya@kestrel.io) is leading the diligence." },
  { icon: ReceiptText, title: "Invoice email", text: "Draft a short email to Ananya Iyer at ananya@northwind.in saying the ₹45,000 invoice for Project Banyan will be paid on Friday." },
]
const PREVIEW_MS = 1100 // how long Mask & send shows what will go out before sending

type Phase = null | "masking" | "sending" | "revealing"
const PHASE_TEXT: Record<Exclude<Phase, null>, string> = {
  masking: "Finding sensitive details…",
  sending: "Muse Spark is thinking…",
  revealing: "Continuing with your decision…",
}

export function ChatView({ chatId, onChat, panelOpen, onTogglePanel }: {
  chatId: string | null; onChat: (id: string) => void; panelOpen: boolean; onTogglePanel: () => void
}) {
  const qc = useQueryClient()
  const [input, setInput] = useState("")
  const [preview, setPreview] = useState<(MaskResult & { original: string }) | null>(null)
  const [pending, setPending] = useState<{ text: string; spans: MaskResult["spans"] } | null>(null)
  const [autoSend, setAutoSend] = useState(false)
  const [ask, setAsk] = useState<Ask | null>(null)
  const [phase, setPhase] = useState<Phase>(null)
  const threadRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const detail = useQuery({ queryKey: ["chat", chatId], queryFn: () => engine.chatDetail(chatId!), enabled: !!chatId })
  const health = useQuery({ queryKey: ["health"], queryFn: engine.health })
  const chats = useQuery({ queryKey: ["chats"], queryFn: engine.chats })
  const vault = useQuery({ queryKey: ["vault", chatId], queryFn: () => engine.vault(chatId!), enabled: !!chatId })
  const messages = useMemo(() => (chatId ? detail.data?.messages ?? [] : []), [chatId, detail.data])
  const title = chats.data?.find((c) => c.chat_id === chatId)?.title
  const maskedCount = (vault.data?.entities.length ?? 0) + (vault.data?.contexts.length ?? 0)

  const kinds = useMemo(() => {
    const k: Record<string, string> = {}
    for (const m of messages) {
      for (const s of m.meta.spans ?? []) k[s.placeholder] = s.kind
      for (const s of m.segments ?? []) if (s.label && s.kind) k[s.label] = s.kind
    }
    return k
  }, [messages])

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" })
  }, [messages.length, ask, pending, phase])

  // Auto-grow the composer up to ~8 lines.
  useLayoutEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = "0px"
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`
  }, [input])

  const refresh = (id: string) => {
    for (const key of [["chat", id], ["vault", id], ["chats"], ["metrics"]]) qc.invalidateQueries({ queryKey: key })
  }

  const afterTurn = async (t: Turn) => {
    if (t.chat_id) {
      onChat(t.chat_id)
      refresh(t.chat_id)
      await qc.refetchQueries({ queryKey: ["chat", t.chat_id] })
    }
    setPending(null)
    if (t.error) toast.error(t.error)
    setAsk(t.ask)
  }

  async function mask(text: string) {
    setPhase("masking")
    const m = await engine.mask(text, chatId)
    if (!m.analysis_ok) throw new Error(`Not sent: ${m.error}`)
    setPreview({ ...m, original: text })
    if (!chatId) onChat(m.chat_id)
    qc.invalidateQueries({ queryKey: ["chats"] })
    return m
  }

  async function run(fn: () => Promise<void>) {
    if (phase) return
    try {
      await fn()
    } catch (e) {
      toast.error((e as Error).message)
      setPending(null)
    } finally {
      setPhase(null)
      setAutoSend(false)
    }
  }

  const onPreview = () => run(async () => { if (input.trim()) await mask(input.trim()) })

  const onSend = () =>
    run(async () => {
      const text = input.trim()
      if (!text) return
      const m = await mask(text)
      setAutoSend(true)
      await new Promise((r) => setTimeout(r, PREVIEW_MS))
      setAutoSend(false)
      setPreview(null)
      setInput("")
      setPending({ text, spans: m.spans })
      setPhase("sending")
      await afterTurn(await engine.chat(text, m.chat_id, m.mask_id))
    })

  const onDecide = (decision: "allow" | "deny", level: Level) =>
    run(async () => {
      if (!ask) return
      setPhase("revealing")
      await afterTurn(await engine.reveal(ask, decision, level))
    })

  const empty = messages.length === 0 && !ask && !pending

  return (
    <main className="flex min-h-0 min-w-0 flex-col bg-background">
      {health.data?.analysis && (
        <div className="flex items-center justify-center gap-2 border-b border-warn-foreground/15 bg-warn px-4 py-1.5 text-[12px] text-warn-foreground">
          <FlaskConical className="size-3.5" aria-hidden />
          Prototype mode: finding sensitive details uses Muse Spark on your raw text. Use made-up data only.
        </div>
      )}

      <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b px-5">
        <h1 className="min-w-0 truncate text-[14px] font-semibold tracking-tight">
          {title ? <MaskedText text={title} size="xs" /> : "New chat"}
        </h1>
        <div className="flex items-center gap-2">
          <span className="hidden items-center gap-1.5 rounded-full border bg-card px-2.5 py-1 text-[12px] text-muted-foreground sm:flex">
            <ShieldCheck className="size-3.5 text-masked-line" aria-hidden />
            {maskedCount > 0 ? <><span className="tabular font-medium text-foreground">{maskedCount}</span> items shielded</> : "Shield on"}
          </span>
          <Button variant="ghost" size="icon" aria-label={panelOpen ? "Hide privacy vault" : "Show privacy vault"} aria-pressed={panelOpen}
            onClick={onTogglePanel} className="max-xl:hidden">
            <PanelRight />
          </Button>
        </div>
      </header>

      <section ref={threadRef} className="min-h-0 flex-1 overflow-y-auto" aria-live="polite">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-5 py-8">
          {empty ? <Hero onPick={(t) => { setInput(t); inputRef.current?.focus() }} /> : (
            <>
              {messages.map((m) => <MessageView key={m.message_id} m={m} kinds={kinds} />)}
              {pending && (
                <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
                  <div className="max-w-[min(42rem,85%)] rounded-2xl rounded-br-md bg-primary/[0.07] px-4 py-2.5 text-[14.5px] leading-[1.65] whitespace-pre-wrap ring-1 ring-primary/10 dark:bg-primary/15">
                    <OriginalText text={pending.text} spans={pending.spans} />
                  </div>
                </motion.div>
              )}
              {(phase === "sending" || phase === "revealing") && <Thinking label={PHASE_TEXT[phase]} />}
              <AnimatePresence>{ask && !phase && <AskCard key={ask.ask_id} ask={ask} busy={!!phase} onDecide={onDecide} />}</AnimatePresence>
            </>
          )}
        </div>
      </section>

      <div className="mx-auto w-full max-w-3xl px-5 pb-5">
        <AnimatePresence>
          {preview && (
            <motion.section
              initial={{ opacity: 0, y: 12, height: 0 }}
              animate={{ opacity: 1, y: 0, height: "auto" }}
              exit={{ opacity: 0, y: 8, height: 0 }}
              transition={{ duration: 0.25, ease: [0.2, 0.8, 0.2, 1] }}
              className="overflow-hidden"
            >
              <PreviewCard preview={preview} autoSend={autoSend} onClose={() => setPreview(null)} />
            </motion.section>
          )}
        </AnimatePresence>

        <form
          onSubmit={(e) => { e.preventDefault(); onSend() }}
          className="relative rounded-2xl border bg-card shadow-float transition-shadow focus-within:border-ring/60 focus-within:ring-4 focus-within:ring-ring/10"
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend() } }}
            placeholder="Message Muse Spark. Sensitive details are masked before they leave your device."
            rows={1}
            className="block max-h-[220px] w-full resize-none bg-transparent px-4 pt-3.5 pb-2 text-[14.5px] leading-relaxed outline-none placeholder:text-muted-foreground"
            aria-label="Message"
          />
          <div className="flex items-center justify-between gap-2 px-3 pb-2.5">
            <span className="flex min-w-0 items-center gap-1.5 text-[12px] text-muted-foreground" aria-live="polite">
              {phase ? (
                <><ShieldPulse /> <span className="truncate">{PHASE_TEXT[phase]}</span></>
              ) : (
                <><Lock className="size-3.5" aria-hidden /> <span className="truncate">Enter to shield & send · Shift + Enter for a new line</span></>
              )}
            </span>
            <div className="flex shrink-0 items-center gap-1.5">
              <Button type="button" variant="ghost" size="sm" disabled={!!phase || !input.trim()} onClick={onPreview}>
                <ScanEye /> Preview
              </Button>
              <Button type="submit" size="sm" disabled={!!phase || !input.trim()} className="gap-1.5 pr-3">
                <ShieldCheck /> Shield & send <ArrowUp className="opacity-70" />
              </Button>
            </div>
          </div>
        </form>
      </div>
    </main>
  )
}

function PreviewCard({ preview, autoSend, onClose }: { preview: MaskResult & { original: string }; autoSend: boolean; onClose: () => void }) {
  const counts = preview.spans.reduce<Record<string, number>>((acc, s) => {
    const k = s.kind === "context" ? "passage" : (s.role && s.role !== "OTHER" ? s.role : s.type).toLowerCase().replace(/_/g, " ")
    acc[k] = (acc[k] ?? 0) + 1
    return acc
  }, {})
  const kinds = Object.fromEntries(preview.spans.map((s) => [s.placeholder, s.kind]))
  return (
    <div className="mb-3 overflow-hidden rounded-2xl border bg-card shadow-soft">
      <div className="flex items-center gap-2 border-b px-4 py-2.5">
        <ShieldCheck className="size-4 text-masked-line" aria-hidden />
        <strong className="text-[13px] font-semibold tracking-tight">What Muse Spark will receive</strong>
        <div className="ml-2 hidden flex-wrap gap-1 sm:flex">
          {Object.entries(counts).map(([k, n]) => (
            <span key={k} className="tabular rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">{n} {k}</span>
          ))}
        </div>
        <span className="tabular ml-auto text-[11.5px] text-muted-foreground">
          {Math.round(preview.latency_ms)} ms{preview.cost_usd != null && ` · $${preview.cost_usd.toFixed(4)}`}
        </span>
        {!autoSend && (
          <button type="button" aria-label="Close preview" onClick={onClose} className="grid size-6 place-items-center rounded-md text-muted-foreground hover:bg-muted">
            <X className="size-3.5" />
          </button>
        )}
      </div>
      <div className="grid max-h-52 grid-cols-2 gap-0 overflow-y-auto max-md:grid-cols-1">
        <div className="border-r px-4 py-3 max-md:border-r-0 max-md:border-b">
          <div className="mb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">You wrote</div>
          <div className="text-[13.5px] leading-relaxed whitespace-pre-wrap break-words"><OriginalText text={preview.original} spans={preview.spans} /></div>
        </div>
        <div className="bg-subtle px-4 py-3">
          <div className="mb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Sent</div>
          <div className="text-[13.5px] leading-relaxed whitespace-pre-wrap break-words"><MaskedText text={preview.masked_text} kinds={kinds} /></div>
        </div>
      </div>
      {autoSend && (
        <motion.div className="h-0.5 origin-left bg-primary" initial={{ scaleX: 0 }} animate={{ scaleX: 1 }}
          transition={{ duration: PREVIEW_MS / 1000, ease: "linear" }} />
      )}
    </div>
  )
}

function Hero({ onPick }: { onPick: (text: string) => void }) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }} className="pt-[8vh] text-center">
      <span className="relative mx-auto grid size-14 place-items-center">
        <span className="absolute inset-0 rounded-2xl bg-primary/20 blur-xl" />
        <span className="relative grid size-14 place-items-center rounded-2xl bg-gradient-to-br from-primary to-[oklch(0.55_0.2_300)] text-primary-foreground shadow-float">
          <ShieldCheck className="size-7" aria-hidden />
        </span>
      </span>
      <h2 className="mt-6 text-[26px] font-semibold tracking-[-0.02em] text-balance">Ask anything. Your secrets stay here.</h2>
      <p className="mx-auto mt-2 max-w-lg text-[14.5px] leading-relaxed text-pretty text-muted-foreground">
        Names, IDs, amounts and whole confidential passages are swapped for placeholders before Muse Spark sees them,
        then put back into the answer on your device.
      </p>
      <div className="mx-auto mt-6 flex max-w-xl flex-wrap justify-center gap-x-5 gap-y-2 text-[12.5px] text-muted-foreground">
        <Trust icon={ScanEye} text="You see exactly what’s sent" />
        <Trust icon={KeyRound} text="Encrypted local vault" />
        <Trust icon={ShieldCheck} text="Nothing hidden is shared without your OK" />
      </div>
      <div className="mt-8 grid gap-3 text-left sm:grid-cols-3">
        {EXAMPLES.map(({ icon: Icon, title, text }, i) => (
          <motion.button
            key={title}
            type="button"
            onClick={() => onPick(text)}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08 + i * 0.06 }}
            whileHover={{ y: -2 }}
            className="group rounded-xl border bg-card p-3.5 text-left shadow-soft transition-colors hover:border-primary/40"
          >
            <span className="mb-2.5 grid size-8 place-items-center rounded-lg bg-accent text-accent-foreground">
              <Icon className="size-4" aria-hidden />
            </span>
            <div className="text-[13px] font-semibold tracking-tight">{title}</div>
            <div className="mt-1 line-clamp-3 text-[12.5px] leading-snug text-muted-foreground">{text}</div>
          </motion.button>
        ))}
      </div>
    </motion.div>
  )
}

function Trust({ icon: Icon, text }: { icon: typeof ShieldCheck; text: string }) {
  return <span className="flex items-center gap-1.5"><Icon className="size-3.5 text-primary" aria-hidden />{text}</span>
}

function Thinking({ label }: { label: string }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-3">
      <span className="grid size-7 place-items-center rounded-full bg-gradient-to-br from-primary to-[oklch(0.6_0.18_300)] text-primary-foreground shadow-soft">
        <Sparkles className="size-3.5" aria-hidden />
      </span>
      <span className="flex items-center gap-2 text-[13px] text-muted-foreground">
        <span className="flex gap-1" aria-hidden>
          {[0, 1, 2].map((i) => (
            <motion.span key={i} className="size-1.5 rounded-full bg-primary/70"
              animate={{ opacity: [0.3, 1, 0.3], y: [0, -2, 0] }} transition={{ duration: 1, repeat: Infinity, delay: i * 0.15 }} />
          ))}
        </span>
        {label}
      </span>
    </motion.div>
  )
}

function ShieldPulse() {
  return (
    <motion.span animate={{ scale: [1, 1.15, 1], opacity: [0.7, 1, 0.7] }} transition={{ duration: 1.2, repeat: Infinity }}
      className={cn("inline-flex text-primary")}>
      <ShieldCheck className="size-3.5" aria-hidden />
    </motion.span>
  )
}
