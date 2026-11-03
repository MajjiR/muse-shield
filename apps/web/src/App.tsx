import { ChatView } from "@/components/chat-view"
import { PrivacyPanel } from "@/components/privacy-panel"
import { Sidebar } from "@/components/sidebar"
import { cn } from "@/lib/utils"
import { useState } from "react"

export default function App() {
  const [chatId, setChatId] = useState<string | null>(null)
  // Bumped only when the user switches or starts a chat, so ChatView's local state (preview,
  // pending ask) resets then, and not when sending assigns an id to a brand-new chat.
  const [view, setView] = useState(0)
  const [panelOpen, setPanelOpen] = useState(true)
  const open = (id: string | null) => {
    setChatId(id)
    setView((v) => v + 1)
  }
  return (
    <div
      className={cn(
        "grid h-dvh bg-background text-foreground max-md:grid-cols-1",
        panelOpen ? "grid-cols-[272px_minmax(0,1fr)] xl:grid-cols-[272px_minmax(0,1fr)_320px]" : "grid-cols-[272px_minmax(0,1fr)]",
      )}
    >
      <Sidebar chatId={chatId} onSelect={open} onNew={() => open(null)} />
      <ChatView key={view} chatId={chatId} onChat={setChatId} panelOpen={panelOpen} onTogglePanel={() => setPanelOpen((p) => !p)} />
      {panelOpen && <PrivacyPanel chatId={chatId} />}
    </div>
  )
}
