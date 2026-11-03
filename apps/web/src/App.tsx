import { ChatView } from "@/components/chat-view"
import { Sidebar } from "@/components/sidebar"
import { useState } from "react"

export default function App() {
  const [chatId, setChatId] = useState<string | null>(null)
  // Bumped only when the user switches or starts a chat, so ChatView's local state (preview,
  // pending ask) resets then, and not when sending assigns an id to a brand-new chat.
  const [view, setView] = useState(0)
  const open = (id: string | null) => {
    setChatId(id)
    setView((v) => v + 1)
  }
  return (
    <div className="grid h-dvh grid-cols-[260px_minmax(0,1fr)] bg-background text-foreground max-md:grid-cols-1">
      <Sidebar chatId={chatId} onSelect={open} onNew={() => open(null)} />
      <ChatView key={view} chatId={chatId} onChat={setChatId} />
    </div>
  )
}
