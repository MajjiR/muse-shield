import { MaskedText } from "@/components/privacy-text"
import { engine } from "@/lib/engine"
import { cn } from "@/lib/utils"
import type { ChatSummary } from "@muse-shield/core"
import { useQuery } from "@tanstack/react-query"
import { Monitor, Moon, PenSquare, Search, ShieldCheck, Sun } from "lucide-react"
import { motion } from "motion/react"
import { useTheme } from "next-themes"
import { useMemo, useState } from "react"

function groupChats(chats: ChatSummary[]) {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  const today = start.getTime() / 1000
  const week = today - 6 * 86400
  const groups: [string, ChatSummary[]][] = [["Today", []], ["Previous 7 days", []], ["Older", []]]
  for (const c of chats) groups[c.created_at >= today ? 0 : c.created_at >= week ? 1 : 2][1].push(c)
  return groups.filter(([, list]) => list.length)
}

export function Sidebar({ chatId, onSelect, onNew }: { chatId: string | null; onSelect: (id: string) => void; onNew: () => void }) {
  const chats = useQuery({ queryKey: ["chats"], queryFn: engine.chats })
  const health = useQuery({ queryKey: ["health"], queryFn: engine.health, refetchInterval: 15000 })
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: engine.metrics })
  const [q, setQ] = useState("")
  const filtered = useMemo(
    () => (chats.data ?? []).filter((c) => c.title.toLowerCase().includes(q.toLowerCase())),
    [chats.data, q],
  )
  const h = health.data

  return (
    <aside className="flex min-h-0 flex-col border-r border-sidebar-border bg-sidebar max-md:hidden">
      <div className="flex items-center justify-between px-4 pt-4 pb-3">
        <div className="flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-primary to-[oklch(0.55_0.2_300)] text-primary-foreground shadow-soft">
            <ShieldCheck className="size-4.5" aria-hidden />
          </span>
          <div className="leading-tight">
            <div className="text-[14px] font-semibold tracking-tight">Muse Shield</div>
            <div className="text-[11px] text-muted-foreground">Private AI workspace</div>
          </div>
        </div>
        <button type="button" onClick={onNew} aria-label="New chat"
          className="grid size-8 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground">
          <PenSquare className="size-4" />
        </button>
      </div>

      <div className="px-3 pb-2">
        <label className="flex items-center gap-2 rounded-lg border border-sidebar-border bg-card px-2.5 py-1.5 text-muted-foreground focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/20">
          <Search className="size-3.5" aria-hidden />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search chats"
            className="w-full bg-transparent text-[13px] text-foreground outline-none placeholder:text-muted-foreground" />
        </label>
      </div>

      <nav aria-label="Chats" className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-2 py-2">
        {chats.data?.length === 0 && (
          <p className="px-3 py-6 text-center text-[13px] text-muted-foreground">Your chats will show up here.</p>
        )}
        {groupChats(filtered).map(([label, list]) => (
          <div key={label}>
            <div className="px-2.5 pb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{label}</div>
            {list.map((c) => {
              const active = c.chat_id === chatId
              return (
                <button key={c.chat_id} type="button" onClick={() => onSelect(c.chat_id)}
                  className={cn("relative w-full rounded-lg px-2.5 py-2 text-left transition-colors",
                    active ? "bg-sidebar-accent" : "hover:bg-sidebar-accent/60")}>
                  {active && <motion.span layoutId="chat-active" className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-primary" />}
                  <span className="block truncate text-[13px] leading-snug text-sidebar-foreground">
                    <MaskedText text={c.title} size="xs" />
                  </span>
                  <span className="tabular mt-0.5 block text-[11px] text-muted-foreground">
                    {c.messages} {c.messages === 1 ? "message" : "messages"} · {new Date(c.created_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </button>
              )
            })}
          </div>
        ))}
      </nav>

      <div className="m-3 space-y-2 rounded-xl border border-sidebar-border bg-card p-3 text-[12px] shadow-soft">
        {health.isError && <p className="text-destructive">Engine unreachable</p>}
        {h && (
          <>
            <Status ok={h.analysis} label="Masking" value={h.analysis_model ?? "off"} />
            <Status ok={h.chat} label="Answers" value={h.chat_model ?? "off"} />
          </>
        )}
        <div className="flex items-center justify-between border-t pt-2 text-muted-foreground">
          <span className="tabular">{metrics.data ? `$${metrics.data.cost_total.toFixed(4)} · ${metrics.data.inspector.requests} calls` : "–"}</span>
          <ThemeSwitch />
        </div>
      </div>
    </aside>
  )
}

function Status({ ok, label, value }: { ok: boolean; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-2 text-muted-foreground">
        <span className="relative flex size-2">
          {ok && <span className="absolute inline-flex size-full animate-ping rounded-full bg-masked-line opacity-40" />}
          <span className={cn("relative inline-flex size-2 rounded-full", ok ? "bg-masked-line" : "bg-destructive")} />
        </span>
        {label}
      </span>
      <span className="truncate font-mono text-[11px]">{value}</span>
    </div>
  )
}

function ThemeSwitch() {
  const { theme, setTheme } = useTheme()
  const opts = [["light", Sun], ["dark", Moon], ["system", Monitor]] as const
  return (
    <div className="flex rounded-md bg-muted p-0.5" role="radiogroup" aria-label="Theme">
      {opts.map(([t, Icon]) => (
        <button key={t} type="button" role="radio" aria-checked={theme === t} aria-label={`${t} theme`} onClick={() => setTheme(t)}
          className={cn("grid size-6 place-items-center rounded-[5px] transition-colors",
            theme === t ? "bg-card text-foreground shadow-soft" : "text-muted-foreground hover:text-foreground")}>
          <Icon className="size-3.5" />
        </button>
      ))}
    </div>
  )
}
