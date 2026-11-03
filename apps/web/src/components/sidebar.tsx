import { Button } from "@/components/ui/button"
import { engine } from "@/lib/engine"
import { cn } from "@/lib/utils"
import { useQuery } from "@tanstack/react-query"
import { Plus, ShieldCheck } from "lucide-react"

export function Sidebar({ chatId, onSelect, onNew }: { chatId: string | null; onSelect: (id: string) => void; onNew: () => void }) {
  const chats = useQuery({ queryKey: ["chats"], queryFn: engine.chats })
  const health = useQuery({ queryKey: ["health"], queryFn: engine.health, refetchInterval: 15000 })
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: engine.metrics })
  const h = health.data

  return (
    <aside className="flex min-h-0 flex-col gap-3 border-r bg-sidebar p-3.5 max-md:hidden">
      <div className="flex items-center gap-2 px-1 text-[15px] font-semibold">
        <ShieldCheck className="size-5 text-primary" aria-hidden /> Muse Shield
      </div>
      <Button onClick={onNew} className="w-full"><Plus /> New chat</Button>
      <nav aria-label="Chats" className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto">
        {chats.data?.length === 0 && <p className="px-2 py-1 text-xs text-muted-foreground">No chats yet</p>}
        {chats.data?.map((c) => (
          <button
            key={c.chat_id}
            type="button"
            onClick={() => onSelect(c.chat_id)}
            className={cn("rounded-lg px-2.5 py-2 text-left hover:bg-sidebar-accent", c.chat_id === chatId && "bg-sidebar-accent")}
          >
            <span className={cn("block truncate font-mono text-xs", c.chat_id === chatId && "font-semibold")}>{c.title}</span>
            <span className="block text-[11px] text-muted-foreground">
              {c.messages} messages · {new Date(c.created_at * 1000).toLocaleString()}
            </span>
          </button>
        ))}
      </nav>
      <div className="space-y-1 border-t pt-2.5 text-[11px] text-muted-foreground">
        {health.isError && <p className="text-destructive">engine unreachable</p>}
        {h && (
          <>
            <p><Dot ok={h.analysis} /> masking: {h.analysis_model ?? "off"}</p>
            <p><Dot ok={h.chat} /> chat: {h.chat_model ?? "off"}</p>
          </>
        )}
        {metrics.data && (
          <p>spent ${metrics.data.cost_total.toFixed(4)} · {metrics.data.inspector.requests} requests</p>
        )}
      </div>
    </aside>
  )
}

function Dot({ ok }: { ok: boolean }) {
  return <span className={cn("mr-1.5 inline-block size-[7px] rounded-full align-[1px]", ok ? "bg-masked-line" : "bg-destructive")} />
}
