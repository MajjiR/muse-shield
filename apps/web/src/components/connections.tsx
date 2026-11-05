import { Button } from "@/components/ui/button"
import { engine } from "@/lib/engine"
import { cn } from "@/lib/utils"
import type { Connections, ConnectionStatus } from "@muse-shield/core"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, FileText, FolderOpen, Loader2, Mail, Send, X } from "lucide-react"
import { motion } from "motion/react"
import { useEffect, useRef, useState } from "react"
import { toast } from "sonner"

/** Sign in to Gmail/Calendar/Contacts and Telegram, and pick a documents folder. Opened from the sidebar. */
export function ConnectionsDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const conns = useQuery({ queryKey: ["connections"], queryFn: engine.connections })
  const refresh = () => qc.invalidateQueries({ queryKey: ["connections"] })
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose()
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])
  const c = conns.data

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-foreground/20 p-4 backdrop-blur-[2px]" onClick={onClose}>
      <motion.div
        role="dialog" aria-modal="true" aria-labelledby="connections-title"
        initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 380, damping: 30 }}
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[90dvh] w-full max-w-xl flex-col overflow-hidden rounded-md border bg-card shadow-soft"
      >
        <div className="flex items-start justify-between gap-3 border-b px-5 py-4">
          <div>
            <h2 id="connections-title" className="font-heading text-[22px] leading-tight font-normal">Connections</h2>
            <p className="mt-0.5 text-[13px] text-muted-foreground">
              Sign in once. Muse Shield reads and acts for you with everything masked, and every send waits for your OK.
            </p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="grid size-7 shrink-0 place-items-center rounded-md text-muted-foreground hover:bg-muted">
            <X className="size-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4">
          {!c ? (
            <p className="flex items-center gap-2 text-[13px] text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Checking connections…</p>
          ) : (
            <>
              <GoogleCard status={c.google} onChange={refresh} />
              <TelegramCard status={c.telegram} onChange={refresh} />
              <FolderCard folder={c.folder} onChange={refresh} />
            </>
          )}
        </div>

        <p className="border-t bg-subtle px-5 py-3 text-[11.5px] leading-snug text-muted-foreground">
          Sign-ins are kept encrypted in your vault on this device.
          Finding what to hide sends the text to your masking model's deployment, so use test accounts while prototyping.
        </p>
      </motion.div>
    </div>
  )
}

function Card({ icon: Icon, title, status, children }: {
  icon: typeof Mail; title: string; status: ConnectionStatus | { connected: boolean; account?: string | null; services?: string[] }
  children: React.ReactNode
}) {
  return (
    <section className={cn("rounded-md border px-4 py-3", status.connected && "border-foreground/30")}>
      <div className="flex items-center gap-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-sm bg-muted"><Icon className="size-4" aria-hidden /></span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-[14px] font-semibold tracking-tight">
            {title}
            {status.connected
              ? <span className="flex items-center gap-1 rounded-sm border px-1.5 text-[11px] font-medium"><Check className="size-3" /> Connected</span>
              : <span className="rounded-sm border border-dashed px-1.5 text-[11px] font-normal text-muted-foreground">Not connected</span>}
          </div>
          <div className="truncate text-[12.5px] text-muted-foreground">
            {status.connected && status.account ? status.account : (status.services ?? []).join(" · ")}
          </div>
        </div>
      </div>
      <div className="mt-3">{children}</div>
    </section>
  )
}

function NotInBuild({ what }: { what: string }) {
  return <p className="text-[12.5px] text-muted-foreground">{what} sign-in isn’t set up in this build yet (the app’s {what} key is missing).</p>
}

function GoogleCard({ status, onChange }: { status: ConnectionStatus; onChange: () => void }) {
  const [waiting, setWaiting] = useState(false)
  const timer = useRef<number | null>(null)
  useEffect(() => () => { if (timer.current) window.clearInterval(timer.current) }, [])
  useEffect(() => {
    if (waiting && status.connected) {
      setWaiting(false)
      if (timer.current) window.clearInterval(timer.current)
      toast.success(`Google connected${status.account ? ` as ${status.account}` : ""}`)
    }
  }, [waiting, status.connected, status.account])

  const connect = async () => {
    try {
      const { url } = await engine.googleStart()
      window.open(url, "_blank", "noopener,width=520,height=680")
      setWaiting(true)
      const started = Date.now()
      timer.current = window.setInterval(() => {
        onChange()
        if (Date.now() - started > 5 * 60_000 && timer.current) { window.clearInterval(timer.current); setWaiting(false) }
      }, 2000)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  const disconnect = async () => {
    if (!window.confirm("Disconnect Google? Muse Shield forgets the sign-in and asks Google to revoke it.")) return
    await engine.disconnect("google")
    onChange()
  }

  return (
    <Card icon={Mail} title="Google" status={status}>
      {!status.configured ? <NotInBuild what="Google" />
        : status.connected ? (
          <div className="flex items-center justify-between gap-2">
            <span className="text-[12.5px] text-muted-foreground">Gmail, Calendar and Contacts now come from your account.</span>
            <Button variant="ghost" size="sm" onClick={disconnect}>Disconnect</Button>
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2">
            <span className="text-[12.5px] text-muted-foreground">
              {waiting ? "Finish signing in in the Google tab…" : "Read and send mail, see and move events, look up contacts."}
            </span>
            <Button size="sm" onClick={connect} disabled={waiting}>{waiting && <Loader2 className="animate-spin" />} Connect Google</Button>
          </div>
        )}
    </Card>
  )
}

function TelegramCard({ status, onChange }: { status: ConnectionStatus; onChange: () => void }) {
  const [phone, setPhone] = useState("")
  const [code, setCode] = useState("")
  const [password, setPassword] = useState("")
  const [needsPassword, setNeedsPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const step = needsPassword ? "password" : status.step === "code" ? "code" : "phone"

  const run = async (fn: () => Promise<ConnectionStatus>) => {
    setBusy(true)
    try {
      const s = await fn()
      if (s.step === "password") setNeedsPassword(true)
      if (s.connected) { setNeedsPassword(false); setCode(""); setPassword(""); toast.success(`Telegram connected as ${s.account}`) }
      onChange()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const disconnect = async () => {
    if (!window.confirm("Disconnect Telegram? Muse Shield logs this session out and forgets it.")) return
    await engine.disconnect("telegram")
    onChange()
  }

  return (
    <Card icon={Send} title="Telegram" status={status}>
      {!status.configured ? <NotInBuild what="Telegram" />
        : status.connected ? (
          <div className="flex items-center justify-between gap-2">
            <span className="text-[12.5px] text-muted-foreground">Your chats are readable masked; messages send only after your OK.</span>
            <Button variant="ghost" size="sm" onClick={disconnect}>Disconnect</Button>
          </div>
        ) : (
          <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => {
            e.preventDefault()
            run(() => step === "phone" ? engine.telegramStart(phone) : engine.telegramVerify(code, password))
          }}>
            {step === "phone" && <Field label="Phone number" value={phone} onChange={setPhone} placeholder="+91 98765 43210" type="tel" autoComplete="tel" />}
            {step === "code" && <Field label="Login code from Telegram" value={code} onChange={setCode} placeholder="12345" inputMode="numeric" autoComplete="one-time-code" />}
            {step === "password" && <Field label="Two-step password" value={password} onChange={setPassword} type="password" autoComplete="current-password" />}
            <Button size="sm" type="submit" disabled={busy || !(step === "phone" ? phone : step === "code" ? code : password)}>
              {busy && <Loader2 className="animate-spin" />} {step === "phone" ? "Send code" : "Sign in"}
            </Button>
          </form>
        )}
    </Card>
  )
}

function FolderCard({ folder, onChange }: { folder: Connections["folder"]; onChange: () => void }) {
  const [value, setValue] = useState("")
  const [busy, setBusy] = useState<null | "type" | "browse">(null)
  const path = folder.path
  const run = async (how: "type" | "browse") => {
    setBusy(how)
    try {
      await (how === "browse" ? engine.pickFolder() : engine.chooseFolder(value))
      setValue("")
      onChange()
    } catch (e) {
      const msg = (e as Error).message
      if (!msg.includes("no folder chosen")) toast.error(msg)
    } finally {
      setBusy(null)
    }
  }
  return (
    <Card icon={FolderOpen} title="Folders and files" status={{ connected: !!path, account: path, services: ["Documents", "PDFs", "Spreadsheets"] }}>
      {path ? (
        <div className="space-y-2">
          {folder.files && (
            <div className="rounded-md border bg-subtle px-3 py-2">
              <div className="mb-1 text-[11.5px] text-muted-foreground">
                <span className="tabular font-medium text-foreground">{folder.files.count}</span> file{folder.files.count === 1 ? "" : "s"} Muse Shield can open
              </div>
              <ul className="space-y-0.5">
                {folder.files.names.map((n) => (
                  <li key={n} className="flex items-center gap-1.5 truncate font-mono text-[12px]"><FileText className="size-3 shrink-0" aria-hidden />{n}</li>
                ))}
                {folder.files.count > folder.files.names.length && (
                  <li className="text-[11.5px] text-muted-foreground">and {folder.files.count - folder.files.names.length} more</li>
                )}
              </ul>
            </div>
          )}
          <div className="flex items-center justify-between gap-2">
            <span className="text-[12.5px] text-muted-foreground">Files are masked when read; totals are worked out on this device.</span>
            <div className="flex gap-1">
              {folder.can_browse && <Button variant="ghost" size="sm" disabled={!!busy} onClick={() => run("browse")}>Change…</Button>}
              <Button variant="ghost" size="sm" onClick={async () => { await engine.disconnect("folder"); onChange() }}>Disconnect</Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          {folder.can_browse && (
            <Button size="sm" disabled={!!busy} onClick={() => run("browse")}>
              {busy === "browse" ? <Loader2 className="animate-spin" /> : <FolderOpen />} Choose a folder…
            </Button>
          )}
          <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); run("type") }}>
            <Field label={folder.can_browse ? "Or type its path" : "Folder on this computer"} value={value} onChange={setValue} placeholder="~/Documents/Finance" />
            <Button size="sm" variant="outline" type="submit" disabled={!!busy || !value}>{busy === "type" && <Loader2 className="animate-spin" />} Use folder</Button>
          </form>
          <p className="text-[11.5px] text-muted-foreground">PDF, Word, PowerPoint, text, CSV and TSV files, in this folder and its subfolders.</p>
        </div>
      )}
    </Card>
  )
}

function Field({ label, value, onChange, ...rest }: { label: string; value: string; onChange: (v: string) => void } &
  Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  return (
    <label className="flex min-w-0 flex-1 flex-col gap-1 text-[11.5px] text-muted-foreground">
      {label}
      <input {...rest} value={value} onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-input bg-background px-2.5 py-1.5 text-[13.5px] text-foreground outline-none focus:border-foreground/50" />
    </label>
  )
}
