import { MaskedText } from "@/components/privacy-text"
import { engine } from "@/lib/engine"
import { modeShort } from "@/lib/modes"
import { cn, modelLabel } from "@/lib/utils"
import type { ChatSummary } from "@muse-shield/core"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { PenSquare, Plug, Search, ShieldCheck, Trash2 } from "lucide-react"
import { motion } from "motion/react"
import { useMemo, useState } from "react"
import { toast } from "sonner"

function groupChats(chats: ChatSummary[]) {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  const today = start.getTime() / 1000
  const week = today - 6 * 86400
  const groups: [string, ChatSummary[]][] = [["Today", []], ["Previous 7 days", []], ["Older", []]]
  for (const c of chats) groups[c.created_at >= today ? 0 : c.created_at >= week ? 1 : 2][1].push(c)
  return groups.filter(([, list]) => list.length)
}

export function Sidebar({ chatId, onSelect, onNew, onConnections }: {
  chatId: string | null; onSelect: (id: string) => void; onNew: () => void; onConnections: () => void
}) {
  const connections = useQuery({ queryKey: ["connections"], queryFn: engine.connections })
  const linked = connections.data ? [connections.data.google, connections.data.telegram, connections.data.folder].filter((c) => c.connected).length : 0
  const chats = useQuery({ queryKey: ["chats"], queryFn: engine.chats })
  const health = useQuery({ queryKey: ["health"], queryFn: engine.health, refetchInterval: 15000 })
  const [q, setQ] = useState("")
  const qc = useQueryClient()
  const remove = async (id: string, title: string) => {
    if (!window.confirm(`Delete "${title}"? Its messages, files, images and the real values only it uses are removed from the vault. This can't be undone.`)) return
    try {
      await engine.deleteChat(id)
      if (id === chatId) onNew()
      qc.removeQueries({ queryKey: ["chat", id] })
      await qc.invalidateQueries({ queryKey: ["chats"] })
      toast.success("Chat deleted")
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  const filtered = useMemo(
    () => (chats.data ?? []).filter((c) => c.title.toLowerCase().includes(q.toLowerCase())),
    [chats.data, q],
  )
  const h = health.data

  return (
    <aside className="flex min-h-0 flex-col border-r border-sidebar-border bg-sidebar max-md:hidden">
      <div className="flex items-center justify-between px-4 pt-4 pb-3">
        <div className="flex items-center gap-2.5">
          <span className="grid size-7 place-items-center rounded-sm bg-foreground text-background">
            <ShieldCheck className="size-4" aria-hidden />
          </span>
          <div className="leading-tight">
            <div className="font-heading text-[21px] leading-none font-normal tracking-[-0.01em]">Muse Shield</div>
            <div className="mt-1 font-mono text-[11px] tracking-[-0.01em] text-muted-foreground">Private AI workspace</div>
          </div>
        </div>
        <button type="button" onClick={onNew} aria-label="New chat"
          className="grid size-8 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground">
          <PenSquare className="size-4" />
        </button>
      </div>

      <div className="px-3 pb-2">
        <label className="flex items-center gap-2 rounded-md border border-sidebar-border bg-card px-2.5 py-1.5 text-muted-foreground focus-within:border-foreground/50">
          <Search className="size-3.5" aria-hidden />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search chats"
            className="w-full bg-transparent text-[14px] text-foreground outline-none placeholder:text-muted-foreground" />
        </label>
      </div>

      <nav aria-label="Chats" className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-2 py-2">
        {chats.data?.length === 0 && (
          <p className="px-3 py-6 text-center text-[13px] text-muted-foreground">Your chats will show up here.</p>
        )}
        {groupChats(filtered).map(([label, list]) => (
          <div key={label}>
            <div className="px-2.5 pb-1 eyebrow text-muted-foreground">{label}</div>
            {list.map((c) => {
              const active = c.chat_id === chatId
              return (
                <div key={c.chat_id} className="group relative">
                <button type="button" onClick={() => onSelect(c.chat_id)}
                  className={cn("relative w-full rounded-md py-2 pr-9 pl-2.5 text-left transition-colors",
                    active ? "bg-sidebar-accent" : "hover:bg-sidebar-accent/60")}>
                  {active && <motion.span layoutId="chat-active" className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-primary" />}
                  <span className="block truncate text-[14px] leading-snug text-sidebar-foreground">
                    <MaskedText text={c.title} plain />
                  </span>
                  <span className="tabular mt-0.5 block text-[11px] text-muted-foreground">
                    {c.messages} {c.messages === 1 ? "message" : "messages"} · {new Date(c.created_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    {c.mode && <> · {modeShort(c.mode)}</>}
                  </span>
                </button>
                <button type="button" aria-label={`Delete chat ${c.title}`} title="Delete chat" onClick={() => remove(c.chat_id, c.title)}
                  className="absolute top-2 right-1.5 grid size-7 place-items-center rounded-md text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 hover:bg-background hover:text-foreground">
                  <Trash2 className="size-3.5" />
                </button>
                </div>
              )
            })}
          </div>
        ))}
      </nav>

      <button type="button" onClick={onConnections}
        className="mx-3 flex items-center justify-between gap-2 rounded-md border border-sidebar-border bg-card px-3 py-2 text-left text-[13px] transition-colors hover:bg-subtle">
        <span className="flex items-center gap-2"><Plug className="size-4" aria-hidden /> Connections</span>
        <span className="tabular text-[11.5px] text-muted-foreground">{linked ? `${linked} connected` : "Sample data"}</span>
      </button>

      <div className="m-3 space-y-2 rounded-md border border-sidebar-border bg-card p-3 text-[12px]">
        {health.isError && <p className="font-medium">Engine unreachable</p>}
        {h && (
          <>
            <Status ok={h.analysis} label="Masking" value={modelLabel(h.analysis_model)} />
            <Status ok={h.chat} label="Answers" value={h.chat_model ?? "off"} />
          </>
        )}
      </div>
    </aside>
  )
}

function Status({ ok, label, value }: { ok: boolean; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-2 text-muted-foreground">
        <span className="relative flex size-2">
                    <span className={cn("relative inline-flex size-2 rounded-full", ok ? "bg-foreground" : "border border-foreground bg-transparent")} />
        </span>
        {label}
      </span>
      <span className="truncate font-mono text-[11px]">{value}</span>
    </div>
  )
}
