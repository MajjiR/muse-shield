import { AskCard } from "@/components/ask-card"
import { MessageView } from "@/components/message"
import { MaskedText, OriginalText } from "@/components/privacy-text"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { engine } from "@/lib/engine"
import type { Ask, Level, MaskResult, Turn } from "@muse-shield/core"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2, X } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"

const EXAMPLES = [
  "My name is Rohan and I earn 10 lakh rupees. Tomorrow I'm planning to buy a land at 12-4, MVP Colony, Visakhapatnam. Is that a sensible plan on my salary?",
  "Confidential: Acme Corp has agreed to acquire Kestrel Labs for ₹120 crore. Priya Shah (priya@kestrel.io) is leading the diligence.",
  "Draft a short email to Ananya Iyer at ananya@northwind.in saying the ₹45,000 invoice for Project Banyan will be paid on Friday.",
]
const PREVIEW_MS = 900 // how long Mask & send shows what will go out before sending

type Phase = null | "masking" | "sending" | "revealing"
const PHASE_TEXT: Record<Exclude<Phase, null>, string> = {
  masking: "Masking on Muse Spark…",
  sending: "Sending the masked message to Muse Spark…",
  revealing: "Answering with what you decided…",
}

export function ChatView({ chatId, onChat }: { chatId: string | null; onChat: (id: string) => void }) {
  const qc = useQueryClient()
  const [input, setInput] = useState("")
  const [preview, setPreview] = useState<(MaskResult & { original: string }) | null>(null)
  const [ask, setAsk] = useState<Ask | null>(null)
  const [phase, setPhase] = useState<Phase>(null)
  const threadRef = useRef<HTMLDivElement>(null)

  const detail = useQuery({ queryKey: ["chat", chatId], queryFn: () => engine.chatDetail(chatId!), enabled: !!chatId })
  const health = useQuery({ queryKey: ["health"], queryFn: engine.health })
  const chats = useQuery({ queryKey: ["chats"], queryFn: engine.chats })
  const messages = useMemo(() => (chatId ? detail.data?.messages ?? [] : []), [chatId, detail.data])
  const title = chats.data?.find((c) => c.chat_id === chatId)?.title ?? "New chat"

  // Which placeholders are context blocks, so chips get the right colour.
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
  }, [messages.length, ask])

  const refresh = (id: string) => {
    qc.invalidateQueries({ queryKey: ["chat", id] })
    qc.invalidateQueries({ queryKey: ["chats"] })
    qc.invalidateQueries({ queryKey: ["metrics"] })
  }

  const afterTurn = (t: Turn) => {
    if (t.chat_id) {
      onChat(t.chat_id)
      refresh(t.chat_id)
    }
    if (t.error) toast.error(t.error)
    setAsk(t.ask)
  }

  async function mask(text: string) {
    setPhase("masking")
    const m = await engine.mask(text, chatId)
    if (!m.analysis_ok) throw new Error(`Not sent: ${m.error}`)
    setPreview({ ...m, original: text })
    if (!chatId) onChat(m.chat_id)
    qc.invalidateQueries({ queryKey: ["chats"] }) // the new chat shows up with its masked title right away
    return m
  }

  async function run(fn: () => Promise<void>) {
    if (phase) return
    try {
      await fn()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setPhase(null)
    }
  }

  const onPreview = () => run(async () => { if (input.trim()) await mask(input.trim()) })

  const onSend = () =>
    run(async () => {
      const text = input.trim()
      if (!text) return
      const m = await mask(text)
      await new Promise((r) => setTimeout(r, PREVIEW_MS))
      setPhase("sending")
      const t = await engine.chat(text, m.chat_id, m.mask_id)
      setInput("")
      setPreview(null)
      afterTurn(t)
    })

  const onDecide = (decision: "allow" | "deny", level: Level) =>
    run(async () => {
      if (!ask) return
      setPhase("revealing")
      afterTurn(await engine.reveal(ask, decision, level))
    })

  return (
    <main className="flex min-h-0 min-w-0 flex-col">
      {health.data?.analysis && (
        <div className="border-b border-warn-foreground/30 bg-warn px-5 py-1.5 text-xs text-warn-foreground">
          Prototype mode: masking (call 1) sends your raw text to Muse Spark. Use fake data only.
        </div>
      )}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3">
        <h1 className="max-w-[60%] truncate font-mono text-sm font-semibold">{title}</h1>
        <div className="flex gap-3.5 text-xs text-muted-foreground">
          <Legend className="bg-masked-line" label="masked" />
          <Legend className="bg-context-line" label="context block" />
          <Legend className="bg-kept-line" label="kept" />
        </div>
      </header>

      <section ref={threadRef} className="flex flex-1 flex-col gap-3.5 overflow-y-auto p-5" aria-live="polite">
        {messages.length === 0 && !ask ? (
          <div className="m-auto max-w-xl text-center text-muted-foreground">
            <h2 className="mb-2 text-lg font-semibold text-foreground">Ask anything. Sensitive details stay with you.</h2>
            <p className="text-sm">
              Names, IDs, amounts and whole deal or HR passages are swapped for placeholders before Muse Spark sees them,
              and put back in the reply on this device.
            </p>
            <div className="mt-5 flex flex-col gap-2">
              {EXAMPLES.map((ex) => (
                <button key={ex} type="button" onClick={() => setInput(ex)}
                  className="rounded-xl border bg-card px-3 py-2.5 text-left text-[13px] hover:border-primary">
                  {ex}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) => <MessageView key={m.message_id} m={m} kinds={kinds} />)
        )}
        {ask && <AskCard ask={ask} busy={!!phase} onDecide={onDecide} />}
      </section>

      {preview && (
        <section className="mx-5 rounded-t-xl border border-b-0 bg-card px-3.5 py-2.5">
          <div className="mb-2 flex items-center gap-2.5">
            <strong className="text-sm">What Muse Spark will see</strong>
            <span className="ml-auto text-xs text-muted-foreground">
              {preview.spans.length} masked · {Math.round(preview.latency_ms)} ms
              {preview.cost_usd != null && ` · $${preview.cost_usd.toFixed(4)}`}
            </span>
            <Button size="icon-xs" variant="ghost" aria-label="Close preview" onClick={() => setPreview(null)}><X /></Button>
          </div>
          <div className="grid max-h-44 grid-cols-2 gap-3.5 overflow-y-auto max-md:grid-cols-1">
            <div>
              <div className="mb-1 text-[11px] tracking-wide text-muted-foreground uppercase">Your message</div>
              <div className="whitespace-pre-wrap break-words text-sm"><OriginalText text={preview.original} spans={preview.spans} /></div>
            </div>
            <div>
              <div className="mb-1 text-[11px] tracking-wide text-muted-foreground uppercase">Sent</div>
              <div className="whitespace-pre-wrap break-words font-mono text-xs">
                <MaskedText text={preview.masked_text} kinds={Object.fromEntries(preview.spans.map((s) => [s.placeholder, s.kind]))} />
              </div>
            </div>
          </div>
        </section>
      )}

      <form
        className={`mx-5 mb-4 rounded-xl border bg-card p-2.5 ${preview ? "rounded-t-none" : ""}`}
        onSubmit={(e) => { e.preventDefault(); onSend() }}
      >
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); onSend() } }}
          placeholder="Type a message… (⌘/Ctrl + Enter to mask & send)"
          className="min-h-14 resize-y border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent"
          rows={3}
        />
        <div className="flex items-center justify-end gap-2">
          <span className="mr-auto text-xs text-muted-foreground" aria-live="polite">
            {phase && <><Loader2 className="mr-1.5 inline size-3 animate-spin" />{PHASE_TEXT[phase]}</>}
          </span>
          <Button type="button" variant="outline" disabled={!!phase} onClick={onPreview}>Preview mask</Button>
          <Button type="submit" disabled={!!phase}><span aria-hidden>■■</span> Mask &amp; send</Button>
        </div>
      </form>
    </main>
  )
}

function Legend({ className, label }: { className: string; label: string }) {
  return <span className="flex items-center gap-1.5"><i className={`inline-block size-2.5 rounded-[3px] ${className}`} />{label}</span>
}
