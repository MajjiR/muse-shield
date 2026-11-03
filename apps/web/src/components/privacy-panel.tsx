import { Chip } from "@/components/privacy-text"
import { engine } from "@/lib/engine"
import { cn } from "@/lib/utils"
import { useQuery } from "@tanstack/react-query"
import { Eye, EyeOff, KeyRound, Link2, Lock, ShieldCheck, ShieldX } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { useState } from "react"

const TYPE_LABEL: Record<string, string> = {
  PERSON: "People", ORG: "Organisations", CONTACT: "Contact details", ID: "IDs & numbers", ADDRESS: "Addresses",
  LOCATION: "Places", AMOUNT: "Amounts", DATE: "Dates", SECRET: "Secrets", SENSITIVE_ATTRIBUTE: "Sensitive details", PROJECT: "Projects",
}

export function PrivacyPanel({ chatId }: { chatId: string | null }) {
  const [tab, setTab] = useState<"vault" | "consents">("vault")
  const vault = useQuery({ queryKey: ["vault", chatId], queryFn: () => engine.vault(chatId!), enabled: !!chatId })
  const detail = useQuery({ queryKey: ["chat", chatId], queryFn: () => engine.chatDetail(chatId!), enabled: !!chatId })
  const entities = vault.data?.entities ?? []
  const contexts = vault.data?.contexts ?? []
  const consents = detail.data?.consents ?? []
  const groups = Object.entries(
    entities.reduce<Record<string, typeof entities>>((acc, e) => ((acc[e.type] ??= []).push(e), acc), {}),
  ).sort((a, b) => b[1].length - a[1].length)

  return (
    <aside className="flex min-h-0 flex-col border-l bg-sidebar max-xl:hidden" aria-label="Privacy panel">
      <div className="border-b px-4 pt-4 pb-3">
        <div className="flex items-center gap-2 text-[13px] font-semibold tracking-tight">
          <Lock className="size-3.5" aria-hidden /> Privacy vault
        </div>
        <p className="mt-0.5 text-[12px] text-muted-foreground">Encrypted on this device. Only placeholders leave it.</p>
        <div className="mt-3 grid grid-cols-3 gap-2">
          <Stat label="Values" value={entities.length} />
          <Stat label="Passages" value={contexts.length} />
          <Stat label="Shared" value={consents.filter((c) => c.decision === "allow").length} />
        </div>
        <div className="mt-3 inline-flex w-full rounded-md bg-muted p-1" role="tablist">
          {(["vault", "consents"] as const).map((t) => (
            <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
              className={cn("relative flex-1 rounded-md py-1 text-[12.5px] font-medium transition-colors",
                tab === t ? "text-foreground" : "text-muted-foreground hover:text-foreground")}>
              {tab === t && <motion.span layoutId="panel-tab" className="absolute inset-0 rounded-md bg-card shadow-soft" />}
              <span className="relative">{t === "vault" ? "Masked items" : "Consent log"}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {!chatId ? (
          <Empty icon={<KeyRound className="size-5" />} text="Start a chat to see what gets masked and kept in your vault." />
        ) : tab === "vault" ? (
          entities.length + contexts.length === 0 ? (
            <Empty icon={<KeyRound className="size-5" />} text="Nothing masked in this chat yet." />
          ) : (
            <div className="space-y-5">
              {contexts.length > 0 && (
                <Section title="Hidden passages">
                  {contexts.map((c) => (
                    <div key={c.label} className="rounded-md border bg-card p-2.5">
                      <div className="flex items-center justify-between gap-2">
                        <Chip label={c.label} context size="xs" />
                        <span className="text-[11px] text-muted-foreground">{(c.subtype ?? c.kind).toLowerCase().replace(/_/g, " ")}</span>
                      </div>
                      {c.summary && <p className="mt-1.5 text-[12.5px] leading-snug text-muted-foreground">{c.summary}</p>}
                      <Reveal chatId={chatId} label={c.label} />
                    </div>
                  ))}
                </Section>
              )}
              {groups.map(([type, list]) => (
                <Section key={type} title={TYPE_LABEL[type] ?? type} count={list.length}>
                  {list.map((e) => (
                    <div key={e.label} className="rounded-md border bg-card px-2.5 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <Chip label={e.label} size="xs" />
                        {e.chats > 1 && (
                          <span className="flex items-center gap-1 text-[11px] text-muted-foreground" title="The same value appears in other chats">
                            <Link2 className="size-3" aria-hidden /> {e.chats} chats
                          </span>
                        )}
                      </div>
                      <Reveal chatId={chatId} label={e.label} />
                    </div>
                  ))}
                </Section>
              ))}
            </div>
          )
        ) : consents.length === 0 ? (
          <Empty icon={<ShieldCheck className="size-5" />} text="Muse Spark hasn’t asked for anything hidden in this chat." />
        ) : (
          <ol className="relative space-y-3 border-l pl-4">
            {consents.map((c, i) => (
              <li key={i} className="relative">
                <span className={cn("absolute top-1 -left-[21px] grid size-3 place-items-center rounded-full ring-4 ring-sidebar",
                  c.decision === "allow" ? "bg-foreground" : "border border-foreground bg-sidebar")} />
                <div className="flex items-center gap-1.5 text-[12.5px] font-medium">
                  {c.decision === "allow" ? <ShieldCheck className="size-3.5" /> : <ShieldX className="size-3.5" />}
                  {c.decision === "allow" ? "Shared" : "Declined"} <span className="font-mono text-[11px]">{c.label}</span> · {c.level}
                </div>
                {c.reason && <p className="mt-0.5 text-[12px] text-muted-foreground">“{c.reason}”</p>}
                <p className="tabular mt-0.5 text-[11px] text-muted-foreground">{new Date(c.ts * 1000).toLocaleTimeString()}</p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </aside>
  )
}

function Reveal({ chatId, label }: { chatId: string; label: string }) {
  const [value, setValue] = useState<string | null>(null)
  const toggle = async () => {
    if (value !== null) return setValue(null)
    setValue((await engine.vaultReveal(chatId, label)).value)
  }
  return (
    <>
      <button type="button" onClick={toggle}
        className="mt-1.5 flex items-center gap-1 text-[11.5px] font-medium text-foreground underline-offset-2 hover:underline">
        {value === null ? <Eye className="size-3" /> : <EyeOff className="size-3" />}
        {value === null ? "Reveal on this device" : "Hide"}
      </button>
      <AnimatePresence>
        {value !== null && (
          <motion.p initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
            className="mt-1 overflow-hidden rounded-md bg-muted px-2 py-1.5 text-[12.5px] break-words">
            {value}
          </motion.p>
        )}
      </AnimatePresence>
    </>
  )
}

function Section({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 flex items-center justify-between text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
        {title} {count != null && <span className="tabular">{count}</span>}
      </h3>
      <div className="space-y-1.5">{children}</div>
    </section>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border bg-card px-2.5 py-1.5">
      <div className="tabular text-[17px] font-semibold tracking-tight">{value}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  )
}

function Empty({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-10 text-center text-[13px] text-muted-foreground">
      <span className="grid size-9 place-items-center rounded-md border">{icon}</span>
      {text}
    </div>
  )
}
