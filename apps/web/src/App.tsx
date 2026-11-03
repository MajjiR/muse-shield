import { ChatView } from "@/components/chat-view"
import { Sidebar } from "@/components/sidebar"
import { useState } from "react"

export default function App() {
  const [chatId, setChatId] = useState<string | null>(null)
  return (
    <div className="grid h-dvh grid-cols-[260px_minmax(0,1fr)] bg-background text-foreground max-md:grid-cols-1">
      <Sidebar chatId={chatId} onSelect={setChatId} onNew={() => setChatId(null)} />
      <ChatView chatId={chatId} onChat={setChatId} />
    </div>
  )
}
