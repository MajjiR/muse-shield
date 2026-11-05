import { ActionCard, StepLine, toolMeta } from "@/components/action-card"
import { AskCard } from "@/components/ask-card"
import { CategoryLine, ModeBadge, ModePicker } from "@/components/categories"
import { DocumentCard } from "@/components/document-card"
import { ImageCard, PendingImageCard } from "@/components/image-card"
import { MessageView } from "@/components/message"
import { MaskedText, OriginalText } from "@/components/privacy-text"
import { toneForType, toneVars, type Tone } from "@/lib/tones"
import { Button } from "@/components/ui/button"
import { engine } from "@/lib/engine"
import { cn } from "@/lib/utils"
import type { Ask, AskChoice, DocumentInfo, ImageInfo, Level, MaskMode, MaskResult, Turn } from "@muse-shield/core"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowUp, Briefcase, FileUp, HeartPulse, Landmark, Mail, PanelRight, Paperclip, ShieldCheck, Sparkles, Wrench,
} from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"

const EXAMPLES = [
  { icon: Mail, title: "Draft an email", text: "Draft a polite email to my landlord Suresh Kulkarni (suresh.kulkarni@gmail.com) asking to pay this month's rent of ₹38,000 a week late, because my salary from Infosys is delayed." },
  { icon: Landmark, title: "File my taxes", text: "I'm filing my ITR for FY 2025-26. PAN ABCPM1234K, salary ₹18,40,000, ₹1,50,000 in ELSS and ₹42,000 health insurance for my parents. Is the old or the new regime better for me?" },
  { icon: Briefcase, title: "M&A deal update", text: "Confidential: Acme Corp will acquire Kestrel Labs for ₹120 crore, closing 15 December. Priya Shah (priya@kestrel.io) leads diligence. Write a two-line update for our board." },
  { icon: HeartPulse, title: "Understand a report", text: "My mother Sunita Verma, 64, has a TSH of 6.8 and takes levothyroxine 50 mcg from Dr. Kavita Rao at Lotus Clinic. What should I ask at her next appointment?" },
]
const PREVIEW_MS = 1100 // how long a sent message shows what was found before it goes out

type Phase = null | "masking" | "sending" | "revealing" | "acting"
type Pending = { text: string; stage: "analysing" | "masked" | "sending"; masked?: MaskResult }

const PHASE_TEXT: Record<Exclude<Phase, null>, string> = {
  masking: "Analysing for sensitive details…",
  sending: "Muse Spark is thinking…",
  revealing: "Continuing with your decision…",
  acting: "Running it on your device…",
}

export function ChatView({ chatId, onChat, panelOpen, onTogglePanel }: {
  chatId: string | null; onChat: (id: string) => void; panelOpen: boolean; onTogglePanel: () => void
}) {
  const qc = useQueryClient()
  const [input, setInput] = useState("")
  const [pending, setPending] = useState<Pending | null>(null)
  // The mode a NEW chat starts in (remembered per browser); an existing chat stays in the mode it's locked to.
  const [newMode, setNewMode] = useState<MaskMode | null>(() => {
    try { return localStorage.getItem("ms-chat-mode") } catch { return null }
  })
  const chooseMode = (m: MaskMode) => {
    setNewMode(m)
    try { localStorage.setItem("ms-chat-mode", m) } catch { /* private window: keep it for this session only */ }
  }
  const [ask, setAsk] = useState<Ask | null>(null)
  const [phase, setPhase] = useState<Phase>(null)
  const threadRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  // Documents uploaded for the next message: masked in the background, sent with it.
  const [attached, setAttached] = useState<DocumentInfo[]>([])
  const [docStatus, setDocStatus] = useState<Record<string, DocumentInfo["status"]>>({})
  // Images are masked while you wait (~20-30 s); the pending ones show a blurred local preview.
  const [images, setImages] = useState<ImageInfo[]>([])
  const [pendingImages, setPendingImages] = useState<{ key: string; filename: string; previewUrl: string }[]>([])
  const [dragging, setDragging] = useState(false)

  const detail = useQuery({ queryKey: ["chat", chatId], queryFn: () => engine.chatDetail(chatId!), enabled: !!chatId })
  const health = useQuery({ queryKey: ["health"], queryFn: engine.health })
  const chats = useQuery({ queryKey: ["chats"], queryFn: engine.chats })
  const vault = useQuery({ queryKey: ["vault", chatId], queryFn: () => engine.vault(chatId!), enabled: !!chatId })
  const actions = useQuery({ queryKey: ["actions", chatId], queryFn: () => engine.actions(chatId!), enabled: !!chatId })
  const actionById = useMemo(() => Object.fromEntries((actions.data ?? []).map((a) => [a.action_id, a])), [actions.data])
  const messages = useMemo(() => (chatId ? detail.data?.messages ?? [] : []), [chatId, detail.data])
  // How each tool call ended, from the thread itself (used when the engine restarted and no longer has the action).
  const endedAs = useMemo(() => Object.fromEntries(messages.filter((m) => m.role === "tool_result" && m.meta.action_id)
    .map((m) => [m.meta.action_id!, m.meta.status ?? "finished"])), [messages])
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
  }, [input, attached.length, images.length, pendingImages.length]) // the placeholder and layout change with attachments

  const refresh = (id: string) => {
    for (const key of [["chat", id], ["vault", id], ["actions", id], ["outbox", id], ["chats"], ["metrics"], ["audit-chain"]]) {
      qc.invalidateQueries({ queryKey: key })
    }
  }

  const afterTurn = async (t: Turn) => {
    if (t.chat_id) {
      onChat(t.chat_id)
      refresh(t.chat_id)
      await Promise.all([qc.refetchQueries({ queryKey: ["chat", t.chat_id] }), qc.refetchQueries({ queryKey: ["actions", t.chat_id] })])
    }
    setPending(null)
    if (t.error) toast.error(t.error)
    setAsk(t.ask)
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
    }
  }

  const docsAllowed = !!health.data?.analysis && health.data?.documents !== false
  const modes = health.data?.modes ?? []
  const chatMode = chatId ? (detail.data?.mode ?? chats.data?.find((c) => c.chat_id === chatId)?.mode ?? null) : null
  const startMode = modes.some((m) => m.id === newMode) ? newMode : health.data?.default_mode ?? null
  const mode: MaskMode | null = chatId ? null : startMode // the server keeps an existing chat's own mode
  const imagesAllowed = !!health.data?.images
  const filesAllowed = docsAllowed || imagesAllowed
  const statusOf = (d: DocumentInfo) => docStatus[d.doc_id] ?? d.status
  const sendable = attached.filter((d) => ["ready", "blocked"].includes(statusOf(d)))
  const docsBusy = attached.some((d) => !["ready", "blocked", "failed"].includes(statusOf(d))) || pendingImages.length > 0
  const canSend = !phase && !docsBusy && (!!input.trim() || sendable.length > 0 || images.length > 0)
  const accept = [docsAllowed && ".pdf,.docx,.pptx", imagesAllowed && "image/png,image/jpeg,image/webp,image/gif"].filter(Boolean).join(",")

  async function upload(files: FileList | File[]) {
    let cid = chatId
    const list = Array.from(files)
    if (!cid && list.length > 1) {  // several files into a new conversation: one chat for all of them
      cid = (await engine.newChat(mode)).chat_id
      onChat(cid)
    }
    const adopt = (id: string) => {
      if (!cid) {
        cid = id
        onChat(id)
      }
      qc.invalidateQueries({ queryKey: ["chats"] })
    }
    for (const file of list) {
      const isImage = /^image\/(png|jpe?g|webp|gif)$/i.test(file.type) || /\.(png|jpe?g|webp|gif)$/i.test(file.name)
      const isDoc = /\.(pdf|docx|pptx)$/i.test(file.name)
      if ((isImage && !imagesAllowed) || (isDoc && !docsAllowed) || (!isImage && !isDoc)) {
        toast.error(`${file.name}: ${[docsAllowed && "PDF, Word or PowerPoint files", imagesAllowed && "PNG, JPEG, WebP or GIF images"].filter(Boolean).join(", or ")} only`)
        continue
      }
      if (isImage) {
        const key = `${file.name}-${file.size}-${Date.now()}`
        const previewUrl = URL.createObjectURL(file)
        setPendingImages((p) => [...p, { key, filename: file.name, previewUrl }])
        engine.uploadImage(file, cid)
          .then((img) => { adopt(img.chat_id); setImages((a) => [...a, img]) })
          .catch((e) => toast.error(`${file.name}: ${(e as Error).message}`))
          .finally(() => { setPendingImages((p) => p.filter((x) => x.key !== key)); URL.revokeObjectURL(previewUrl) })
        continue
      }
      try {
        const d = await engine.uploadDocument(file, cid)
        adopt(d.chat_id)
        setAttached((a) => [...a, d])
      } catch (e) {
        toast.error(`${file.name}: ${(e as Error).message}`)
      }
    }
  }

  // Files already in the thread: deleted from the vault (with their message) after a confirm.
  const deleteSent = async (kind: "document" | "image", id: string, name: string) => {
    if (!window.confirm(`Delete this ${kind} (${name}) from the chat? Its original and masked copy are removed from the vault. This can't be undone.`)) return
    try {
      await (kind === "document" ? engine.deleteDocument(id) : engine.deleteImage(id))
      await qc.invalidateQueries({ queryKey: ["chat", chatId] })
      toast.success(`${kind === "document" ? "Document" : "Image"} deleted`)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  const removeAttached = async (d: DocumentInfo) => {
    setAttached((a) => a.filter((x) => x.doc_id !== d.doc_id))
    await engine.deleteDocument(d.doc_id).catch(() => undefined)
  }

  // Send: the message moves into the thread at once and shimmers while it's analysed; when the
  // result arrives each found detail lights up in its colour, then the masked version is sent.
  const onSend = () =>
    run(async () => {
      if (!canSend) return
      const text = input.trim()
      const docIds = sendable.map((d) => d.doc_id)
      const imageIds = images.map((i) => i.image_id)
      if (docIds.length) setAttached([])
      if (imageIds.length) setImages([])
      if (!text) {
        setPhase("sending")
        await afterTurn(await engine.chat("", chatId, null, docIds, imageIds))
        return
      }
      setInput("")
      setPending({ text, stage: "analysing" })
      setPhase("masking")
      let m: MaskResult
      try {
        m = await engine.mask(text, chatId, mode)
        if (!m.analysis_ok) throw new Error(`Not sent: ${m.error}`)
      } catch (e) {
        setInput(text) // give the text back so nothing is lost
        throw e
      }
      if (!chatId) onChat(m.chat_id)
      qc.invalidateQueries({ queryKey: ["chats"] })
      setPending({ text, stage: "masked", masked: m })
      await new Promise((r) => setTimeout(r, Math.max(PREVIEW_MS, m.spans.length * 110 + 700)))
      setPending({ text, stage: "sending", masked: m })
      setPhase("sending")
      await afterTurn(await engine.chat(text, m.chat_id, m.mask_id, docIds, imageIds))
    })

  const onDecide = (decision: "allow" | "deny", level: Level, items?: Record<string, AskChoice>) =>
    run(async () => {
      if (!ask) return
      setPhase("revealing")
      await afterTurn(await engine.reveal(ask, decision, level, items))
    })

  // Confirm runs the tool here with the real values; cancel drops it. Either way Muse Spark is told how it went.
  const onAction = (actionId: string, decision: "confirm" | "deny") =>
    run(async () => {
      setPhase(decision === "confirm" ? "acting" : "revealing")
      await afterTurn(await engine.decideAction(actionId, decision))
    })

  const empty = messages.length === 0 && !ask && !pending

  return (
    <main
      className="relative flex min-h-0 min-w-0 flex-col bg-background"
      onDragOver={(e) => { if (filesAllowed && e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDragging(true) } }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false) }}
      onDrop={(e) => { if (!filesAllowed) return; e.preventDefault(); setDragging(false); upload(e.dataTransfer.files) }}
    >
      <AnimatePresence>
        {dragging && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="pointer-events-none absolute inset-3 z-40 grid place-items-center rounded-md border-2 border-dashed border-foreground/40 bg-background/90">
            <div className="text-center">
              <FileUp className="mx-auto size-7" aria-hidden />
              <div className="mt-2 text-[15px] font-semibold">Drop {[docsAllowed && "a PDF, Word or PowerPoint file", imagesAllowed && "an image"].filter(Boolean).join(" or ")}</div>
              <div className="text-[13px] text-muted-foreground">Sensitive details are masked before Muse Spark answers</div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      {health.data?.analysis && (
        <div className="flex items-center justify-center gap-2 border-b bg-muted px-4 py-1.5 text-[12px] text-muted-foreground">
          <ShieldCheck className="size-3.5" aria-hidden />
          Masking runs on your fine-tuned Muse Glimmer. Self-host it for full privacy, or use a Fireworks deployment for testing.
        </div>
      )}

      <header className="flex h-[68px] shrink-0 items-center justify-between gap-3 border-b px-5">
        <h1 className="min-w-0 truncate font-heading text-[21px] leading-none font-normal tracking-[-0.01em]">
          {title ? <MaskedText text={title} plain /> : "New chat"}
        </h1>
        <div className="flex items-center gap-2">
          {chatId && <ModeBadge mode={chatMode} modes={modes} />}
          <span className="hidden items-center gap-1.5 rounded-full border border-emerald-600/35 bg-emerald-50 px-3 py-1 text-[12.5px] font-medium text-emerald-700 sm:flex dark:border-emerald-400/30 dark:bg-emerald-950/60 dark:text-emerald-300">
            <ShieldCheck className="size-4" aria-hidden />
            {maskedCount > 0 ? <><span className="tabular">{maskedCount}</span> shielded</> : "Shield on"}
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
              {messages.map((m) => {
                if (m.role === "tool_call") {
                  const a = m.meta.action_id ? actionById[m.meta.action_id] : undefined
                  return a
                    ? <ActionCard key={m.message_id} action={a} busy={!!phase} onDecide={(d) => onAction(a.action_id, d)} />
                    : <StepLine key={m.message_id} icon={Wrench} text={`${toolMeta(m.meta.tool ?? "").done}: ${endedAs[m.meta.action_id ?? ""] ?? "planned"}`} />
                }
                if (m.role === "tool_result") {
                  return m.meta.action_id ? null // its tool call above already shows how it ended
                    : <StepLine key={m.message_id} icon={Wrench} text={`${toolMeta(m.meta.tool ?? "").done}: ${m.meta.status ?? "finished"}`} />
                }
                if (m.role === "document") return m.document
                  ? <DocumentCard key={m.message_id} doc={m.document} onRemove={() => deleteSent("document", m.document!.doc_id, `${m.document!.format.toUpperCase()} ${m.document!.n}`)} />
                  : null
                if (m.role === "image") return m.image
                  ? <ImageCard key={m.message_id} image={m.image} onRemove={() => deleteSent("image", m.image!.image_id, `image ${m.image!.n}`)} />
                  : null
                return <MessageView key={m.message_id} m={m} kinds={kinds} />
              })}
              {pending && <PendingMessage pending={pending} />}
              {(phase === "sending" || phase === "revealing" || phase === "acting") && <Thinking label={PHASE_TEXT[phase]} />}
              <AnimatePresence>{ask && !phase && <AskCard key={ask.ask_id} ask={ask} busy={!!phase} onDecide={onDecide} />}</AnimatePresence>
            </>
          )}
        </div>
      </section>

      <div className="mx-auto w-full max-w-3xl px-5 pb-5">
        {(attached.length > 0 || images.length > 0 || pendingImages.length > 0) && (
          <div className="mb-2 flex max-h-[45vh] flex-col gap-2 overflow-y-auto">
            {pendingImages.map((p) => <PendingImageCard key={p.key} filename={p.filename} previewUrl={p.previewUrl} />)}
            {images.map((i) => (
              <ImageCard key={i.image_id} image={i} align="start" onRemove={() => setImages((a) => a.filter((x) => x.image_id !== i.image_id))} />
            ))}
            {attached.map((d) => (
              <DocumentCard key={d.doc_id} doc={d} align="start" onRemove={() => removeAttached(d)}
                onStatus={(x) => setDocStatus((s) => (s[x.doc_id] === x.status ? s : { ...s, [x.doc_id]: x.status }))} />
            ))}
          </div>
        )}

        {!chatId && modes.length > 1 && startMode && (
          <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
            <span>Masking mode</span>
            <ModePicker modes={modes} value={startMode} onChange={chooseMode} disabled={!!phase} />
            <span className="max-sm:hidden">· set for this chat once you send</span>
          </div>
        )}

        <form
          onSubmit={(e) => { e.preventDefault(); onSend() }}
          className="relative rounded-xl border border-input bg-card shadow-float transition-colors focus-within:border-foreground/60"
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend() } }}
            placeholder={attached.length || images.length ? "Ask about it, or just send it." : "Message Muse Spark. Sensitive details are masked before they leave your device."}
            rows={1}
            className="block max-h-[220px] w-full resize-none bg-transparent px-4 pt-3.5 pb-2 text-[16px] leading-relaxed outline-none placeholder:text-muted-foreground"
            aria-label="Message"
          />
          <div className="flex items-center justify-between gap-2 px-3 pb-2.5">
            <span className="flex min-w-0 items-center gap-1.5 text-[12px] text-muted-foreground" aria-live="polite">
              {phase && <><ShieldPulse /> <span className="truncate">{PHASE_TEXT[phase]}</span></>}
            </span>
            <div className="flex shrink-0 items-center gap-1.5">
              {filesAllowed && (
                <>
                  <input ref={fileRef} type="file" accept={accept} multiple hidden
                    onChange={(e) => { if (e.target.files) upload(e.target.files); e.target.value = "" }} />
                  <Button type="button" variant="ghost" size="icon" aria-label={imagesAllowed ? "Attach a file or an image" : "Attach a PDF, Word or PowerPoint file"} disabled={!!phase}
                    onClick={() => fileRef.current?.click()}>
                    <Paperclip />
                  </Button>
                </>
              )}
              <Button type="submit" size="sm" disabled={!canSend} className="gap-1.5 pr-3">
                <ShieldCheck /> Shield & send <ArrowUp className="opacity-70" />
              </Button>
            </div>
          </div>
        </form>
      </div>
    </main>
  )
}

function PendingMessage({ pending }: { pending: Pending }) {
  const { text, stage, masked } = pending
  const spans = masked?.spans ?? []
  const counts = spans.reduce<Record<string, { n: number; tone: Tone }>>((acc, s) => {
    const label = s.kind === "context" ? "passage" : (s.role && s.role !== "OTHER" ? s.role : s.type).toLowerCase().replace(/_/g, " ")
    const tone = s.kind === "context" ? "context" : toneForType(s.role && s.role !== "OTHER" ? s.role : s.type)
    acc[label] = { n: (acc[label]?.n ?? 0) + 1, tone }
    return acc
  }, {})
  const kinds = Object.fromEntries(spans.map((s) => [s.placeholder, s.kind]))
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col items-end gap-1.5">
      <div className="relative max-w-[min(42rem,85%)] overflow-hidden rounded-md bg-muted px-4 py-2.5 text-[16px] leading-[1.7] whitespace-pre-wrap break-words">
        {stage === "analysing" ? <span className="ms-analysing">{text}</span> : <OriginalText text={text} spans={spans} animate />}
        {stage === "analysing" && (
          <span className="absolute inset-x-0 bottom-0 h-0.5 overflow-hidden bg-border" aria-hidden>
            <span className="block h-full w-1/3 bg-foreground/50" style={{ animation: "ms-progress 1.2s ease-in-out infinite" }} />
          </span>
        )}
      </div>
      <div className="flex max-w-[min(42rem,85%)] flex-wrap items-center justify-end gap-1.5 text-[12px] text-muted-foreground" aria-live="polite">
        {stage === "analysing" ? (
          <span className="flex items-center gap-1.5"><ShieldPulse /> Analysing for sensitive details…</span>
        ) : spans.length === 0 ? (
          <span>Nothing sensitive found</span>
        ) : (
          Object.entries(counts).map(([label, { n, tone }], i) => (
            <motion.span key={label} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 + i * 0.08 }}
              className="tabular flex items-center gap-1 rounded-[3px] border px-1.5 py-px"
              style={{ background: toneVars(tone).bg, borderColor: toneVars(tone).line, color: toneVars(tone).ink }}>
              {n} {label}
            </motion.span>
          ))
        )}
      </div>
      {!!masked?.categories?.length && (
        <CategoryLine categories={masked.categories} summary={masked.summary} className="max-w-[min(42rem,85%)] justify-end" />
      )}
      {masked && spans.length > 0 && (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} transition={{ delay: 0.35 }}
          className="max-w-[min(42rem,85%)] overflow-hidden">
          <div className="border-l-2 border-border pl-3 text-[13.5px] leading-relaxed text-muted-foreground whitespace-pre-wrap">
            <span className="mr-1 eyebrow">Muse Spark receives</span>
            <MaskedText text={masked.masked_text} kinds={kinds} />
          </div>
        </motion.div>
      )}
    </motion.div>
  )
}

function Hero({ onPick }: { onPick: (text: string) => void }) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }} className="pt-[8vh] text-center">
      <span className="relative mx-auto grid size-14 place-items-center">
        <span className="relative grid size-11 place-items-center rounded-md bg-foreground text-background">
          <ShieldCheck className="size-5.5" aria-hidden />
        </span>
      </span>
      <h2 className="mt-6 font-heading text-[46px] leading-[1.1] font-normal tracking-[-0.03em] text-balance">Ask anything. Your secrets stay here.</h2>
      <p className="mx-auto mt-3 max-w-lg text-[16px] leading-relaxed text-pretty text-muted-foreground">
        Your private details are intelligently masked, keeping their context, so Muse Spark still understands and asks you
        when it needs more. The real values come back only on your device.
      </p>
      <div className="mt-8 grid gap-3 text-left sm:grid-cols-2">
        {EXAMPLES.map(({ icon: Icon, title, text }, i) => (
          <motion.button
            key={title}
            type="button"
            onClick={() => onPick(text)}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08 + i * 0.06 }}
            className="group rounded-md border bg-card p-3.5 text-left transition-colors hover:bg-subtle"
          >
            <span className="mb-2.5 grid size-7 place-items-center rounded-sm border text-foreground">
              <Icon className="size-4" aria-hidden />
            </span>
            <div className="text-[15px] font-medium">{title}</div>
            <div className="mt-1 line-clamp-2 text-[13.5px] leading-snug text-muted-foreground">{text}</div>
          </motion.button>
        ))}
      </div>
    </motion.div>
  )
}

function Thinking({ label }: { label: string }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-3">
      <span className="grid size-6 place-items-center rounded-sm bg-foreground text-background">
        <Sparkles className="size-3.5" aria-hidden />
      </span>
      <span className="flex items-center gap-2 text-[13px] text-muted-foreground">
        <span className="flex gap-1" aria-hidden>
          {[0, 1, 2].map((i) => (
            <motion.span key={i} className="size-1.5 rounded-full bg-foreground/60"
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
      className={cn("inline-flex text-foreground")}>
      <ShieldCheck className="size-3.5" aria-hidden />
    </motion.span>
  )
}
